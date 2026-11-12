"""Rebuild the stored profile when it was built under a different language pack."""

from nosolear.app.rebuild_profile import rebuild_profile
from nosolear.domain.packs import LanguagePack
from nosolear.domain.taxonomy import Taxonomy
from nosolear.ports.clock import Clock
from nosolear.ports.stores import ObservationReader, ProfileStore


def ensure_profile_pack(
    *,
    observations: ObservationReader,
    profiles: ProfileStore,
    taxonomy: Taxonomy,
    pack: LanguagePack,
    clock: Clock,
) -> bool:
    """Return True iff a profile existed under another pack and was rebuilt for `pack`."""
    stored = profiles.latest_pack_id()
    if stored is None or stored == pack.id:
        return False
    rebuild_profile(
        observations=observations, profiles=profiles, taxonomy=taxonomy, pack=pack, clock=clock
    )
    return True
