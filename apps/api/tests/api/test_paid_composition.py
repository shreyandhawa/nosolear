from datetime import UTC, datetime

from factories import FixedClock, make_settings
from provider_fakes import FakeScorer, FakeTranscriber, assessment, wrapper_chain
from sqlalchemy import Engine, text
from wavs import write_wav

from nosolear.adapters.retry import RetryingPronunciationScorer, RetryingTranscriber
from nosolear.api.deps import build_ledger, paid_scorer, paid_transcriber
from nosolear.budget.compose import layers_of
from nosolear.budget.meter import Meter
from nosolear.budget.metered_ports import MeteredPronunciationScorer, MeteredTranscriber
from nosolear.domain.errors import RetryableProviderError

T0 = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)


def _ledger(db_engine: Engine, tmp_path):
    return build_ledger(make_settings(data_dir=tmp_path), db_engine, clock=FixedClock(T0))


def ledger_rows(engine: Engine) -> list[tuple[str, int | None]]:
    with engine.connect() as conn:
        return [
            tuple(row)
            for row in conn.execute(text("SELECT state, actual FROM usage_ledger ORDER BY id"))
        ]


def test_paid_scorer_order(db_engine, tmp_path):
    ledger = _ledger(db_engine, tmp_path)
    port = paid_scorer(FakeScorer(), Meter(ledger))
    assert wrapper_chain(port) == [
        RetryingPronunciationScorer,
        MeteredPronunciationScorer,
        FakeScorer,
    ]
    assert layers_of(port) == ["retry", "metered", "raw"]


def test_paid_transcriber_order(db_engine, tmp_path):
    ledger = _ledger(db_engine, tmp_path)
    port = paid_transcriber(FakeTranscriber(), Meter(ledger))
    assert wrapper_chain(port) == [RetryingTranscriber, MeteredTranscriber, FakeTranscriber]
    assert layers_of(port) == ["retry", "metered", "raw"]


def test_every_attempt_reserves(db_engine, tmp_path):
    ledger = _ledger(db_engine, tmp_path)
    wav = write_wav(tmp_path / "a.wav", 2.4)
    fake = FakeScorer(errors=[RetryableProviderError("busy")] * 2, results=[assessment()])
    paid_scorer(fake, Meter(ledger), sleep=lambda s: None).score(wav, reference_text="vest")
    assert len(fake.calls) == 3
    assert ledger_rows(db_engine) == [("recorded", 3)] * 3  # two failures, one success
