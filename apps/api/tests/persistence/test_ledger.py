import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from factories import FixedClock, count, insert_job
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import OperationalError

from nosolear.domain.budget import Caps, Provider, Unit
from nosolear.domain.errors import CapExceeded
from nosolear.persistence.ledger import SqliteUsageLedger
from nosolear.ports.ledger import LedgerError

T0 = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
TOKENS_CAP = 100
CAPS = Caps(azure_audio_seconds=100, azure_tts_chars=100, claude_tokens=100)


def _ledger(engine: Engine, now: datetime = T0, caps: Caps = CAPS) -> SqliteUsageLedger:
    return SqliteUsageLedger(engine, caps=caps, clock=FixedClock(now))


def _rows(engine: Engine) -> list[tuple[object, ...]]:
    with engine.connect() as conn:
        return [
            tuple(r)
            for r in conn.execute(
                text("SELECT provider, unit, state, estimate, actual, period FROM usage_ledger")
            )
        ]


def test_reserve_record_flow(db_engine: Engine):
    ledger = _ledger(db_engine)
    reservation = ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 100)
    ledger.record(reservation, 80)
    usage = ledger.usage(Provider.ANTHROPIC, Unit.TOKENS)
    assert (usage.recorded, usage.reserved, usage.cap) == (80, 0, 100)
    assert usage.period == "2026-11-12"


def test_reserve_over_cap_raises_and_writes_nothing(db_engine: Engine):
    ledger = _ledger(db_engine)
    with pytest.raises(CapExceeded):
        ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, TOKENS_CAP + 1)
    assert count(db_engine, "usage_ledger") == 0


def test_open_reservations_count_against_cap(db_engine: Engine):
    ledger = _ledger(db_engine)
    ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 60)
    with pytest.raises(CapExceeded):
        ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 41)
    ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 40)
    assert ledger.usage(Provider.ANTHROPIC, Unit.TOKENS).reserved == 100


def test_release_frees_headroom(db_engine: Engine):
    ledger = _ledger(db_engine)
    reservation = ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 90)
    ledger.release(reservation)
    usage = ledger.usage(Provider.ANTHROPIC, Unit.TOKENS)
    assert (usage.recorded, usage.reserved) == (0, 0)
    ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 100)


def test_double_settle_is_ledger_error(db_engine: Engine):
    ledger = _ledger(db_engine)
    recorded = ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 10)
    ledger.record(recorded, 5)
    with pytest.raises(LedgerError):
        ledger.record(recorded, 5)
    with pytest.raises(LedgerError):
        ledger.release(recorded)

    released = ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 10)
    ledger.release(released)
    with pytest.raises(LedgerError):
        ledger.record(released, 5)
    with pytest.raises(LedgerError):
        ledger.release(released)


def test_orphans_settle_at_estimate(db_engine: Engine):
    _ledger(db_engine).reserve(Provider.ANTHROPIC, Unit.TOKENS, 50)  # then the process "crashes"
    restarted = _ledger(db_engine)
    assert restarted.settle_open_reservations() == 1
    assert restarted.usage(Provider.ANTHROPIC, Unit.TOKENS).recorded == 50
    assert _rows(db_engine) == [("anthropic", "tokens", "recorded", 50, 50, "2026-11-12")]


def test_period_rolls_over(db_engine: Engine):
    _ledger(db_engine).reserve(Provider.ANTHROPIC, Unit.TOKENS, 100)
    next_day = _ledger(db_engine, now=datetime(2026, 11, 13, 0, 1, tzinfo=UTC))
    assert next_day.usage(Provider.ANTHROPIC, Unit.TOKENS).recorded == 0
    next_day.reserve(Provider.ANTHROPIC, Unit.TOKENS, 100)

    azure_now = _ledger(db_engine, now=datetime(2026, 11, 30, 23, 0, tzinfo=UTC))
    azure_now.reserve(Provider.AZURE, Unit.AUDIO_SECONDS, 100)
    december = _ledger(db_engine, now=datetime(2026, 12, 1, 0, 1, tzinfo=UTC))
    assert december.usage(Provider.AZURE, Unit.AUDIO_SECONDS).reserved == 0
    assert count(db_engine, "usage_ledger") == 3


def test_job_id_is_optional_and_stored(db_engine: Engine):
    insert_job(db_engine, "job-1")
    ledger = _ledger(db_engine)
    ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 1)
    ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 1, job_id="job-1")
    with db_engine.connect() as conn:
        job_ids = conn.execute(text("SELECT job_id FROM usage_ledger ORDER BY id")).scalars().all()
    assert job_ids == [None, "job-1"]


def test_reserve_takes_write_lock_before_reading(db_engine: Engine):
    url = db_engine.url.render_as_string(hide_password=False)
    path = Path(db_engine.url.database or "")
    blocker = sqlite3.connect(path, isolation_level=None)
    impatient = create_engine(url)

    @event.listens_for(impatient, "connect")
    def _short_timeout(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # pyright: ignore[reportAttributeAccessIssue]
        cursor.execute("PRAGMA busy_timeout=50")
        cursor.close()

    try:
        blocker.execute("BEGIN IMMEDIATE")
        ledger = _ledger(impatient)
        with pytest.raises(OperationalError, match="database is locked"):
            ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 1)
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
        impatient.dispose()


def test_threads_cannot_overspend(db_engine: Engine):
    ledger = _ledger(db_engine)
    threads = 8
    barrier = threading.Barrier(threads)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt() -> None:
        barrier.wait()
        try:
            ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 30)
            result = "ok"
        except CapExceeded:
            result = "capped"
        with lock:
            outcomes.append(result)

    workers = [threading.Thread(target=attempt) for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert outcomes.count("ok") == 3
    assert outcomes.count("capped") == 5
    usage = ledger.usage(Provider.ANTHROPIC, Unit.TOKENS)
    assert usage.reserved == 90
