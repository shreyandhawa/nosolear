"""Storage ports the application layer depends on. Adapters live in `persistence`."""

from datetime import datetime
from typing import Protocol

from nosolear.domain.observations import Observation
from nosolear.domain.profile import Profile
from nosolear.domain.speech import ProviderCapabilities, SynthesizedClip


class ObservationReader(Protocol):
    def current(self) -> list[Observation]: ...


class ProfileWriter(Protocol):
    def save(self, profile: Profile, *, session_id: str | None, reason: str) -> str: ...

    def replace(self, profile: Profile) -> None:
        """Replace the current entries with no snapshot."""
        ...

    def snapshot(self, profile: Profile, *, session_id: str | None, reason: str) -> str:
        """Append a snapshot and leave the current entries as they are."""
        ...


class ProfileSnapshotReader(Protocol):
    def latest_snapshot(self, session_id: str, reason: str) -> tuple[str, Profile] | None: ...


class ProfilePackReader(Protocol):
    def latest_pack_id(self) -> str | None: ...


class ProfileStore(ProfileWriter, ProfilePackReader, Protocol):
    """A profile store that can be written and asked which pack its profile was built under."""


class TtsCacheStore(Protocol):
    """One row per clip; the file itself lives at `tts/<hash>.wav` under the data directory."""

    def get(self, hash: str) -> SynthesizedClip | None: ...

    def put(self, clip: SynthesizedClip, *, text: str, created_at: datetime) -> None: ...


class CapabilityWriter(Protocol):
    def add(self, caps: ProviderCapabilities) -> None: ...


class CapabilityReader(Protocol):
    def latest(self, provider: str, adapter: str) -> ProviderCapabilities | None: ...

    def latest_all(self) -> list[ProviderCapabilities]: ...


class SessionCompleter(Protocol):
    def completed_at(self, session_id: str) -> datetime | None: ...

    def claim(self, session_id: str, at: datetime) -> bool:
        """Closes the session only while it is open. True for one of two concurrent calls."""
        ...

    def reopen(self, session_id: str, at: datetime) -> bool:
        """Undoes this call's claim, which completed the session at `at`. Returns whether it did."""
        ...
