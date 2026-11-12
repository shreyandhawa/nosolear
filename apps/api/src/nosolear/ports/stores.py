"""Storage ports the application layer depends on. Adapters live in `persistence`."""

from typing import Protocol

from nosolear.domain.observations import Observation
from nosolear.domain.profile import Profile


class ObservationReader(Protocol):
    def all(self) -> list[Observation]: ...


class ProfileWriter(Protocol):
    def save(self, profile: Profile, *, session_id: str | None, reason: str) -> str: ...


class ProfilePackReader(Protocol):
    def latest_pack_id(self) -> str | None: ...


class ProfileStore(ProfileWriter, ProfilePackReader, Protocol):
    """A profile store that can be written and asked which pack its profile was built under."""
