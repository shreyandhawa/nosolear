"""A single scored moment: one error key, hit or miss, with its weight and provenance."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from numbers import Real

from nosolear.domain.scoring import V0_CONFIG_ID
from nosolear.domain.taxonomy import Detector, Taxonomy


class Outcome(StrEnum):
    MISS = "miss"
    OK = "ok"


class Context(StrEnum):
    SCRIPTED = "scripted"
    UNSCRIPTED = "unscripted"


CONTEXT_WEIGHT: Mapping[Context, float] = {Context.SCRIPTED: 1.0, Context.UNSCRIPTED: 0.5}


class DetectorNotAllowed(ValueError):
    """Raised when a detector may not report on the given error key."""


@dataclass(frozen=True, slots=True)
class Observation:
    error_key: str
    outcome: Outcome
    weight: float
    detector: Detector
    context: Context
    observed_at: datetime
    taxonomy_version: int
    attempt_id: str | None
    evidence: Mapping[str, object]
    scoring_config_id: str = V0_CONFIG_ID
    provisional: bool = False


def make_observation(
    *,
    taxonomy: Taxonomy,
    error_key: str,
    outcome: Outcome,
    detector: Detector,
    context: Context,
    observed_at: datetime,
    confidence: float = 1.0,
    attempt_id: str | None = None,
    evidence: Mapping[str, object] | None = None,
    scoring_config_id: str = V0_CONFIG_ID,
    provisional: bool = False,
) -> Observation:
    definition = taxonomy.get(error_key)
    # Coerce so plain strings become members and unknown values raise ValueError. This is the
    # trust boundary: everything downstream may rely on enum members.
    detector = Detector(detector)
    if detector not in definition.detectors:
        raise DetectorNotAllowed(f"{detector} may not report {error_key}")
    if isinstance(confidence, bool) or not isinstance(confidence, Real):
        raise ValueError(f"confidence must be a real number, got {confidence!r}")
    if not math.isfinite(confidence) or not 0 < confidence <= 1:
        raise ValueError(f"confidence must be in (0, 1], got {confidence}")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    outcome = Outcome(outcome)
    context = Context(context)
    return Observation(
        error_key=error_key,
        outcome=outcome,
        weight=CONTEXT_WEIGHT[context] * confidence,
        detector=detector,
        context=context,
        observed_at=observed_at.astimezone(UTC),
        taxonomy_version=taxonomy.version,
        attempt_id=attempt_id,
        evidence=dict(evidence) if evidence is not None else {},
        scoring_config_id=scoring_config_id,
        provisional=provisional,
    )
