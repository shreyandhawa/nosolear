"""Recompute the learner profile from the full observation log and snapshot it."""

from nosolear.domain.profile import DEFAULT_CONFIG, Profile, ProfileConfig, build_profile
from nosolear.domain.taxonomy import Taxonomy
from nosolear.ports.clock import Clock
from nosolear.ports.stores import ObservationReader, ProfileWriter


def rebuild_profile(
    *,
    observations: ObservationReader,
    profiles: ProfileWriter,
    taxonomy: Taxonomy,
    clock: Clock,
    config: ProfileConfig = DEFAULT_CONFIG,
) -> Profile:
    profile = build_profile(observations.all(), as_of=clock.now(), taxonomy=taxonomy, config=config)
    profiles.save(profile, session_id=None, reason="rebuild")
    return profile
