"""Recompute the learner profile from the full observation log and snapshot it."""

from nosolear.domain.packs import LanguagePack
from nosolear.domain.profile import DEFAULT_CONFIG, Profile, ProfileConfig, build_profile
from nosolear.domain.taxonomy import Taxonomy
from nosolear.ports.clock import Clock
from nosolear.ports.stores import ObservationReader, ProfileWriter


def rebuild_profile(
    *,
    observations: ObservationReader,
    profiles: ProfileWriter,
    taxonomy: Taxonomy,
    pack: LanguagePack,
    clock: Clock,
    config: ProfileConfig = DEFAULT_CONFIG,
    session_id: str | None = None,
    reason: str | None = "rebuild",
) -> Profile:
    """Rebuild from the current observations. A `reason` snapshots the result; None only replaces
    the entries."""
    profile = build_profile(
        observations.current(), as_of=clock.now(), taxonomy=taxonomy, pack=pack, config=config
    )
    if reason is None:
        profiles.replace(profile)
    else:
        profiles.save(profile, session_id=session_id, reason=reason)
    return profile
