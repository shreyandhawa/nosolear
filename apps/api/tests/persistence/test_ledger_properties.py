"""Stateful and differential properties of the usage ledger (ARCHITECTURE.md section 11)."""

import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from factories import FixedClock
from fakes import FakeUsageLedger
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule
from sqlalchemy import Engine

from nosolear.domain.budget import Caps, Provider, Unit
from nosolear.domain.errors import CapExceeded
from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.persistence.ledger import SqliteUsageLedger
from nosolear.ports.ledger import LedgerError, Reservation, UsageLedger

T0 = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
CAP = 100
CAPS = Caps(azure_audio_seconds=CAP, azure_tts_chars=CAP, claude_tokens=CAP)
PROVIDER_OF = {
    Unit.AUDIO_SECONDS: Provider.AZURE,
    Unit.TTS_CHARS: Provider.AZURE,
    Unit.TOKENS: Provider.ANTHROPIC,
}
UNITS = tuple(Unit)


@dataclass
class _Row:
    unit: Unit
    state: str
    estimate: int
    actual: int | None


class _Model:
    """Plain-Python ledger: the same rules written without SQL."""

    def __init__(self) -> None:
        self.rows: dict[int, _Row] = {}

    def totals(self, unit: Unit) -> tuple[int, int]:
        recorded = sum(
            r.actual or 0 for r in self.rows.values() if r.unit is unit and r.state == "recorded"
        )
        reserved = sum(
            r.estimate for r in self.rows.values() if r.unit is unit and r.state == "reserved"
        )
        return recorded, reserved


class LedgerMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self._tmp = tempfile.TemporaryDirectory()
        self.engine: Engine = create_engine_for(f"sqlite:///{Path(self._tmp.name) / 't.sqlite'}")
        upgrade_to_head(self.engine)
        self.ledger: UsageLedger = SqliteUsageLedger(self.engine, caps=CAPS, clock=FixedClock(T0))
        self.model = _Model()
        self.open: list[Reservation] = []
        self.settled: list[Reservation] = []

    def teardown(self) -> None:
        self.engine.dispose()
        self._tmp.cleanup()

    @rule(unit=st.sampled_from(UNITS), estimate=st.integers(min_value=0, max_value=60))
    def reserve(self, unit: Unit, estimate: int) -> None:
        recorded, reserved = self.model.totals(unit)
        fits_by_model = recorded + reserved + estimate <= CAP
        try:
            reservation = self.ledger.reserve(PROVIDER_OF[unit], unit, estimate)
        except CapExceeded:
            assert not fits_by_model
            usage = self.ledger.usage(PROVIDER_OF[unit], unit)
            assert usage.recorded + usage.reserved + estimate > CAP
            return
        assert fits_by_model
        self.open.append(reservation)
        self.model.rows[reservation.id] = _Row(unit, "reserved", estimate, None)

    @precondition(lambda self: bool(self.open))
    @rule(pick=st.integers(min_value=0), actual=st.integers(min_value=0, max_value=60))
    def record(self, pick: int, actual: int) -> None:
        reservation = self.open.pop(pick % len(self.open))
        actual = min(actual, reservation.estimate)  # estimates are upper bounds
        self.ledger.record(reservation, actual)
        row = self.model.rows[reservation.id]
        row.state, row.actual = "recorded", actual
        self.settled.append(reservation)

    @precondition(lambda self: bool(self.open))
    @rule(pick=st.integers(min_value=0))
    def release(self, pick: int) -> None:
        reservation = self.open.pop(pick % len(self.open))
        self.ledger.release(reservation)
        self.model.rows[reservation.id].state = "released"
        self.settled.append(reservation)

    @precondition(lambda self: bool(self.settled))
    @rule(pick=st.integers(min_value=0))
    def settle_twice(self, pick: int) -> None:
        reservation = self.settled[pick % len(self.settled)]
        try:
            self.ledger.record(reservation, 0)
        except LedgerError:
            return
        raise AssertionError("a settled reservation accepted a second record")

    @rule()
    def crash_and_restart(self) -> None:
        orphans = len(self.open)
        self.ledger = SqliteUsageLedger(self.engine, caps=CAPS, clock=FixedClock(T0))
        assert self.ledger.settle_open_reservations() == orphans
        for reservation in self.open:
            row = self.model.rows[reservation.id]
            row.state, row.actual = "recorded", row.estimate
        self.open.clear()

    @invariant()
    def totals_match_the_model_and_stay_under_cap(self) -> None:
        for unit in UNITS:
            usage = self.ledger.usage(PROVIDER_OF[unit], unit)
            recorded, reserved = self.model.totals(unit)
            assert (usage.recorded, usage.reserved) == (recorded, reserved)
            assert usage.recorded + usage.reserved <= usage.cap


TestLedgerStateful = LedgerMachine.TestCase


OPERATIONS = st.lists(
    st.one_of(
        st.tuples(st.just("reserve"), st.sampled_from(UNITS), st.integers(0, 60)),
        st.tuples(st.just("record"), st.integers(0, 50), st.integers(0, 60)),
        st.tuples(st.just("release"), st.integers(0, 50), st.just(0)),
    ),
    max_size=40,
)


def _apply(ledger: UsageLedger, made: list[Reservation], op: tuple[object, ...]) -> object:
    kind, a, b = op
    if kind == "reserve":
        assert isinstance(a, Unit) and isinstance(b, int)
        try:
            made.append(ledger.reserve(PROVIDER_OF[a], a, b))
        except CapExceeded:
            return "capped"
        return "ok"
    assert isinstance(a, int) and isinstance(b, int)
    if not made:
        return "none"
    reservation = made[a % len(made)]
    try:
        if kind == "record":
            ledger.record(reservation, min(b, reservation.estimate))
        else:
            ledger.release(reservation)
    except LedgerError:
        return "ledger_error"
    return "ok"


def _snapshot(ledger: UsageLedger) -> list[tuple[int, int]]:
    return [
        (u.recorded, u.reserved) for u in (ledger.usage(PROVIDER_OF[unit], unit) for unit in UNITS)
    ]


@given(OPERATIONS)
def test_fake_ledger_matches_sqlite_ledger(operations: list[tuple[object, ...]]) -> None:
    clock = FixedClock(T0)
    fake = FakeUsageLedger(CAPS, clock)
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine_for(f"sqlite:///{Path(tmp) / 't.sqlite'}")
        upgrade_to_head(engine)
        real = SqliteUsageLedger(engine, caps=CAPS, clock=clock)
        fake_made: list[Reservation] = []
        real_made: list[Reservation] = []
        try:
            for op in operations:
                assert _apply(fake, fake_made, op) == _apply(real, real_made, op)
                assert _snapshot(fake) == _snapshot(real)
        finally:
            engine.dispose()
