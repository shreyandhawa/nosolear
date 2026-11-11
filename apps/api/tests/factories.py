"""Shared test helpers. Import as `from factories import ...`."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import Engine, text

from nosolear.domain.observations import Context, Observation, Outcome, make_observation
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY, Detector

TAX = DEFAULT_TAXONOMY
T0 = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
DAY = timedelta(days=1)
NOW = T0
NPT = timezone(timedelta(hours=5, minutes=45))


def mk(
    key: str,
    outcome: Outcome,
    at: datetime,
    context: Context = Context.SCRIPTED,
    detector: Detector = Detector.AZURE_PA,
    confidence: float = 1.0,
    evidence: Mapping[str, object] | None = None,
) -> Observation:
    return make_observation(
        taxonomy=TAX,
        error_key=key,
        outcome=outcome,
        detector=detector,
        context=context,
        observed_at=at,
        confidence=confidence,
        evidence=evidence,
    )


SAMPLE_OBS = [
    mk("sound.sub.v.w", Outcome.MISS, T0 - 3 * DAY),
    mk("sound.sub.v.w", Outcome.OK, T0 - 2 * DAY),
    mk("sound.sub.v.w", Outcome.MISS, T0 - DAY, context=Context.UNSCRIPTED),
    mk("sound.sub.θ.t", Outcome.OK, T0 - 2 * DAY),
    mk("sound.sub.θ.t", Outcome.MISS, T0 - DAY),
    mk("fluency.filler", Outcome.MISS, T0 - DAY, detector=Detector.ASR_METRICS, confidence=0.8),
]


def count(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now
