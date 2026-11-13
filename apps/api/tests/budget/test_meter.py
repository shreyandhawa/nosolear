from datetime import UTC, datetime

import pytest
from factories import FixedClock, count, insert_job
from fakes import FakePaidPort, FakeUsageLedger
from sqlalchemy import Engine, text

from nosolear.budget.meter import Meter, metered_method
from nosolear.domain.budget import Caps, Provider, Unit
from nosolear.domain.errors import CapExceeded, RequestNotSent
from nosolear.persistence.ledger import SqliteUsageLedger

T0 = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
CAPS = Caps(azure_audio_seconds=100, azure_tts_chars=100, claude_tokens=100)


def _count(result: int) -> int:
    return result


def _fake() -> tuple[FakeUsageLedger, FakePaidPort, Meter]:
    ledger = FakeUsageLedger(CAPS, FixedClock(T0))
    return ledger, FakePaidPort(), Meter(ledger)


def _call(meter: Meter, port: FakePaidPort, estimate: int, units: int) -> int:
    return meter.call(
        Provider.AZURE,
        Unit.AUDIO_SECONDS,
        estimate,
        lambda: port.run(units),
        actual=lambda n: n,
    )


def test_success_records_actual():
    ledger, port, meter = _fake()
    assert _call(meter, port, estimate=100, units=70) == 70
    usage = ledger.usage(Provider.AZURE, Unit.AUDIO_SECONDS)
    assert (usage.recorded, usage.reserved) == (70, 0)


def test_cap_exceeded_makes_no_call():
    ledger = FakeUsageLedger(
        Caps(azure_audio_seconds=50, azure_tts_chars=50, claude_tokens=50), FixedClock(T0)
    )
    port = FakePaidPort()
    with pytest.raises(CapExceeded):
        Meter(ledger).call(
            Provider.AZURE, Unit.AUDIO_SECONDS, 100, lambda: port.run(100), actual=lambda n: n
        )
    assert port.calls == 0


def test_request_not_sent_releases():
    ledger, port, meter = _fake()
    error = RequestNotSent()
    port.fail_with = error
    with pytest.raises(RequestNotSent) as raised:
        _call(meter, port, estimate=100, units=100)
    assert raised.value is error
    usage = ledger.usage(Provider.AZURE, Unit.AUDIO_SECONDS)
    assert (usage.recorded, usage.reserved) == (0, 0)


def test_other_failure_records_estimate():
    ledger, port, meter = _fake()
    port.fail_with = RuntimeError("boom")
    with pytest.raises(RuntimeError, match="boom"):
        _call(meter, port, estimate=100, units=10)
    usage = ledger.usage(Provider.AZURE, Unit.AUDIO_SECONDS)
    assert (usage.recorded, usage.reserved) == (100, 0)


def test_metered_method_wraps_signature(db_engine: Engine):
    insert_job(db_engine, "job-1")
    ledger = SqliteUsageLedger(db_engine, caps=CAPS, clock=FixedClock(T0))
    meter = Meter(ledger, job_id=lambda: "job-1")

    class Speaker:
        @metered_method(
            meter,
            provider=Provider.ANTHROPIC,
            unit=Unit.TOKENS,
            estimate=lambda self, text, *, extra=0: len(text) + extra,
            actual=_count,
        )
        def speak(self, text: str, *, extra: int = 0) -> int:
            """Doc."""
            return 4

    assert Speaker.speak.__name__ == "speak"
    assert Speaker.speak.__doc__ == "Doc."
    assert Speaker().speak("hi", extra=3) == 4
    with db_engine.connect() as conn:
        row = conn.execute(text("SELECT state, estimate, actual, job_id FROM usage_ledger")).one()
    assert tuple(row) == ("recorded", 5, 4, "job-1")


def test_each_retry_attempt_reserves_on_its_own(db_engine: Engine):
    ledger = SqliteUsageLedger(db_engine, caps=CAPS, clock=FixedClock(T0))
    meter = Meter(ledger)
    port = FakePaidPort()
    port.fail_with = RuntimeError("transient")
    metered = _MeteredFake(meter, port)

    class RetryTwice:
        layer = "retry"

        def __init__(self, inner: _MeteredFake) -> None:
            self.inner = inner

        def run(self, units: int) -> int:
            for _ in range(2):
                try:
                    return self.inner.run(units)
                except RuntimeError:
                    pass
            port.fail_with = None
            return self.inner.run(units)

    assert RetryTwice(metered).run(7) == 7
    assert port.calls == 3
    with db_engine.connect() as conn:
        rows = [
            tuple(r)
            for r in conn.execute(
                text("SELECT state, estimate, actual FROM usage_ledger ORDER BY id")
            )
        ]
    assert rows == [("recorded", 10, 10), ("recorded", 10, 10), ("recorded", 10, 7)]
    assert count(db_engine, "usage_ledger") == 3


class _MeteredFake:
    layer = "metered"

    def __init__(self, meter: Meter, port: FakePaidPort) -> None:
        self._meter = meter
        self._port = port

    def run(self, units: int) -> int:
        return self._meter.call(
            Provider.AZURE,
            Unit.TTS_CHARS,
            10,
            lambda: self._port.run(units),
            actual=lambda n: n,
        )
