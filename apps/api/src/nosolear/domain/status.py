"""Status classification for one key's estimate."""

from dataclasses import dataclass
from enum import StrEnum

from nosolear.domain.estimates import KeyEstimate


class Status(StrEnum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    IMPROVING = "improving"
    WATCHING = "watching"
    MASTERED = "mastered"


@dataclass(frozen=True, slots=True)
class StatusThresholds:
    min_n: float = 5
    active_rate: float = 0.15
    improving_drop: float = 0.30
    improving_lookback_days: float = 14
    mastered_ci_high: float = 0.10
    mastered_min_n: float = 20
    relapse_rate: float = 0.20


def classify(
    est: KeyEstimate,
    *,
    previous: Status | None,
    p_hat_lookback: float | None,
    t: StatusThresholds,
) -> Status:
    if est.n_eff < t.min_n:
        return Status.UNKNOWN
    if previous is Status.MASTERED:
        return Status.ACTIVE if est.p_hat > t.relapse_rate else Status.MASTERED
    if est.ci_high < t.mastered_ci_high and est.n_eff >= t.mastered_min_n:
        return Status.MASTERED
    if est.p_hat >= t.active_rate:
        if p_hat_lookback is not None and est.p_hat <= (1 - t.improving_drop) * p_hat_lookback:
            return Status.IMPROVING
        return Status.ACTIVE
    return Status.WATCHING
