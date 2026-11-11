"""Beta-with-forgetting estimate of one key's miss rate."""

from dataclasses import dataclass
from datetime import datetime

from scipy.stats import beta as beta_dist

from nosolear.domain.observations import Observation, Outcome


@dataclass(frozen=True, slots=True)
class Prior:
    a0: float
    b0: float


HYPOTHESIS_PRIOR = Prior(1, 3)
DEFAULT_PRIOR = Prior(1, 9)


@dataclass(frozen=True, slots=True)
class BetaState:
    a: float
    b: float
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class KeyEstimate:
    p_hat: float
    ci_low: float
    ci_high: float
    n_eff: float


def decay(state: BetaState, *, to: datetime, prior: Prior, half_life_days: float) -> BetaState:
    """Shrink the evidence toward the prior: x <- x0 + (x - x0) * 2^(-days/half_life)."""
    if to < state.updated_at:
        raise ValueError("cannot decay to a time before the state's updated_at")
    days = (to - state.updated_at).total_seconds() / 86400
    factor = 2 ** (-days / half_life_days)
    return BetaState(
        a=prior.a0 + (state.a - prior.a0) * factor,
        b=prior.b0 + (state.b - prior.b0) * factor,
        updated_at=to,
    )


def apply(state: BetaState, obs: Observation) -> BetaState:
    if obs.observed_at < state.updated_at:
        raise ValueError("observation is older than the state it is applied to")
    miss = obs.outcome is Outcome.MISS
    return BetaState(
        a=state.a + (obs.weight if miss else 0.0),
        b=state.b + (0.0 if miss else obs.weight),
        updated_at=obs.observed_at,
    )


def estimate(state: BetaState, *, prior: Prior, level: float) -> KeyEstimate:
    low, high = (1 - level) / 2, (1 + level) / 2
    return KeyEstimate(
        p_hat=state.a / (state.a + state.b),
        ci_low=float(beta_dist.ppf(low, state.a, state.b)),
        ci_high=float(beta_dist.ppf(high, state.a, state.b)),
        n_eff=state.a + state.b - prior.a0 - prior.b0,
    )
