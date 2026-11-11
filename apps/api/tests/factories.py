"""Shared test helpers. Import as `from factories import ...`."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone

from nosolear.domain.observations import Context, Observation, Outcome, make_observation
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY, Detector

TAX = DEFAULT_TAXONOMY
T0 = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
DAY = timedelta(days=1)
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
