import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from factories import FixedClock, make_settings
from sqlalchemy import Engine

from nosolear.adapters.system_clock import SystemClock
from nosolear.api.deps import build_ledger, build_services, read_usage
from nosolear.app.steps import StepRegistry
from nosolear.domain.budget import Caps, Provider, Unit
from nosolear.domain.errors import CapExceeded
from nosolear.domain.readiness import UsageSnapshot
from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.persistence.ledger import SqliteUsageLedger
from nosolear.settings import Settings

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
LONG_AGO = datetime(2020, 1, 1, 12, 0, tzinfo=UTC)
RUNNER_THREAD_PREFIX = "nosolear-job-"


def _migrated(settings: Settings) -> Engine:
    engine = create_engine_for(settings.database_url)
    upgrade_to_head(engine)
    return engine


def _caps(settings: Settings) -> Caps:
    return Caps.from_hours_chars_tokens(
        azure_audio_hours=settings.cap_azure_audio_hours,
        azure_tts_chars=settings.cap_azure_tts_chars,
        claude_tokens=settings.cap_claude_tokens,
    )


def _runner_threads() -> int:
    return sum(
        1 for t in threading.enumerate() if t.name.startswith(RUNNER_THREAD_PREFIX) and t.is_alive()
    )


@pytest.mark.parametrize(("workers", "expected"), [(1, 1), (2, 2)])
def test_job_workers_come_from_settings(tmp_path: Path, workers: int, expected: int) -> None:
    settings = make_settings(data_dir=tmp_path, job_workers=workers)
    engine = _migrated(settings)
    services = build_services(settings, engine, clock=FixedClock(NOW))
    try:
        services.runner.start()
        assert _runner_threads() == expected
    finally:
        services.runner.stop(timeout=10.0)
        engine.dispose()
    assert _runner_threads() == 0


def test_default_job_workers_is_one(tmp_path: Path) -> None:
    assert make_settings(data_dir=tmp_path).job_workers == 1


def test_build_services_uses_the_given_clock_and_registry(tmp_path: Path) -> None:
    settings = make_settings(data_dir=tmp_path)
    engine = _migrated(settings)
    clock = FixedClock(NOW)
    registry = StepRegistry()
    try:
        services = build_services(settings, engine, clock=clock, registry=registry)
        assert services.clock is clock
        assert services.registry is registry
        assert set(services.providers.paid_ports()) == {
            "pronunciation_scorer",
            "synthesizer",
            "coach",
            "transcriber_azure",
        }
    finally:
        services.runner.stop(timeout=10.0)
        engine.dispose()


def test_build_ledger_uses_the_caps_from_settings(tmp_path: Path) -> None:
    settings = make_settings(data_dir=tmp_path, cap_azure_audio_hours=0.001)  # 3.6 seconds
    engine = _migrated(settings)
    try:
        ledger = build_ledger(settings, engine, clock=FixedClock(NOW))
        ledger.reserve(Provider.AZURE, Unit.AUDIO_SECONDS, 3)
        with pytest.raises(CapExceeded):
            ledger.reserve(Provider.AZURE, Unit.AUDIO_SECONDS, 2)
    finally:
        engine.dispose()


def test_read_usage_is_none_without_a_database_and_creates_nothing(tmp_path: Path) -> None:
    data = tmp_path / "data"
    assert read_usage(make_settings(data_dir=data)) is None
    assert not data.exists()


def test_read_usage_is_none_when_the_ledger_table_is_missing(tmp_path: Path) -> None:
    database = tmp_path / "nosolear.sqlite"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE something_else (x INTEGER)")
    assert read_usage(make_settings(data_dir=tmp_path)) is None
    with sqlite3.connect(database) as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    assert names == {"something_else"}, "read_usage must not migrate the database"


def test_read_usage_sums_recorded_and_open_reservations_for_the_current_periods(
    tmp_path: Path,
) -> None:
    settings = make_settings(data_dir=tmp_path)
    engine = _migrated(settings)
    try:
        ledger = SqliteUsageLedger(engine, caps=_caps(settings), clock=SystemClock())
        audio = ledger.reserve(Provider.AZURE, Unit.AUDIO_SECONDS, 3600)
        ledger.record(audio, 1800)
        ledger.reserve(Provider.AZURE, Unit.AUDIO_SECONDS, 1800)  # still open
        tts = ledger.reserve(Provider.AZURE, Unit.TTS_CHARS, 100)
        ledger.record(tts, 40)
        tokens = ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 500)
        ledger.record(tokens, 200)
        ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 300)  # still open
        # a row from another day and month must not count towards today's or this month's figures
        old = SqliteUsageLedger(engine, caps=_caps(settings), clock=FixedClock(LONG_AGO))
        ledger_old = old.reserve(Provider.ANTHROPIC, Unit.TOKENS, 999)
        old.record(ledger_old, 999)
    finally:
        engine.dispose()

    assert read_usage(settings) == UsageSnapshot(
        azure_audio_hours=1.0, tts_chars=40, claude_tokens=500
    )


def test_read_usage_on_a_stopped_server_creates_no_wal_or_shm_files(tmp_path: Path) -> None:
    settings = make_settings(data_dir=tmp_path)
    engine = _migrated(settings)
    try:
        ledger = SqliteUsageLedger(engine, caps=_caps(settings), clock=SystemClock())
        ledger.record(ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 500), 200)
    finally:
        engine.dispose()
    before = sorted(p.name for p in tmp_path.iterdir())

    assert read_usage(settings) == UsageSnapshot(
        azure_audio_hours=0.0, tts_chars=0, claude_tokens=200
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == before
