"""Build a learner profile from observations: one estimate and status per observed key."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from nosolear.domain.estimates import (
    BetaState,
    KeyEstimate,
    apply,
    decay,
    estimate,
)
from nosolear.domain.observations import Observation
from nosolear.domain.packs import LanguagePack
from nosolear.domain.status import Status, StatusThresholds, classify
from nosolear.domain.taxonomy import KeyDefinition, Taxonomy

ALGO_VERSION = 1


@dataclass(frozen=True, slots=True)
class ProfileConfig:
    half_life_days: float = 14.0
    interval_level: float = 0.8
    thresholds: StatusThresholds = field(default_factory=StatusThresholds)


DEFAULT_CONFIG = ProfileConfig()


@dataclass(frozen=True, slots=True)
class ProfileEntry:
    definition: KeyDefinition
    state: BetaState
    estimate: KeyEstimate
    status: Status
    last_seen_at: datetime
    priority: float
    provisional: bool = False


@dataclass(frozen=True, slots=True)
class Profile:
    as_of: datetime
    taxonomy_version: int
    algo_version: int
    pack_id: str
    entries: tuple[ProfileEntry, ...]


def _lookback(history: list[tuple[datetime, float]], at: datetime, days: float) -> float | None:
    """The newest recorded p_hat at or before `days` before `at`."""
    cutoff = at - timedelta(days=days)
    found: float | None = None
    for when, p_hat in history:
        if when > cutoff:
            break
        found = p_hat
    return found


def _build_entry(
    defn: KeyDefinition,
    observations: list[Observation],
    as_of: datetime,
    pack: LanguagePack,
    config: ProfileConfig,
) -> ProfileEntry:
    prior = pack.prior_for(defn.key)
    t = config.thresholds
    state = BetaState(prior.a0, prior.b0, observations[0].observed_at)
    history: list[tuple[datetime, float]] = []
    status: Status | None = None
    for i, obs in enumerate(observations):
        state = apply(
            decay(state, to=obs.observed_at, prior=prior, half_life_days=config.half_life_days),
            obs,
        )
        last_at_timestamp = (
            i + 1 == len(observations) or observations[i + 1].observed_at != obs.observed_at
        )
        if last_at_timestamp:
            est = estimate(state, prior=prior, level=config.interval_level)
            status = classify(
                est,
                previous=status,
                p_hat_lookback=_lookback(history, obs.observed_at, t.improving_lookback_days),
                t=t,
            )
            history.append((obs.observed_at, est.p_hat))
    state = decay(state, to=as_of, prior=prior, half_life_days=config.half_life_days)
    est = estimate(state, prior=prior, level=config.interval_level)
    status = classify(
        est,
        previous=status,
        p_hat_lookback=_lookback(history, as_of, t.improving_lookback_days),
        t=t,
    )
    return ProfileEntry(
        definition=defn,
        state=state,
        estimate=est,
        status=status,
        last_seen_at=observations[-1].observed_at,
        priority=est.p_hat * defn.impact,
        provisional=any(o.provisional for o in observations),
    )


def build_profile(
    observations: Iterable[Observation],
    *,
    as_of: datetime,
    taxonomy: Taxonomy,
    pack: LanguagePack,
    config: ProfileConfig = DEFAULT_CONFIG,
) -> Profile:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    # weight is in the sort key so that tied observations sum in a fixed order (float addition
    # is not associative), which keeps the result independent of input order.
    included = sorted(
        (o for o in observations if o.observed_at <= as_of),
        key=lambda o: (o.observed_at, o.error_key, o.outcome, o.weight),
    )
    by_key: dict[str, list[Observation]] = {}
    for o in included:
        by_key.setdefault(o.error_key, []).append(o)
    entries = [
        _build_entry(taxonomy.get(key), group, as_of, pack, config) for key, group in by_key.items()
    ]
    entries.sort(key=lambda e: (-e.priority, e.definition.key))
    return Profile(
        as_of=as_of,
        taxonomy_version=taxonomy.version,
        algo_version=ALGO_VERSION,
        pack_id=pack.id,
        entries=tuple(entries),
    )
