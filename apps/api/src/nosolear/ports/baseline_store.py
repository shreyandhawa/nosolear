"""The baseline session's port: its session, protocol attempts, scores and completion. Adapters
live in `persistence`."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from nosolear.domain.content import BaselineProtocol
from nosolear.domain.skill_scores import SkillScore
from nosolear.ports.stores import ProfileSnapshotReader, ProfileWriter


@dataclass(frozen=True, slots=True)
class BaselineSessionRecord:
    id: str
    protocol_version: int
    started_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class BaselineItemRecord:
    attempt_id: str
    order: int
    item_id: str
    step: str
    scripted: bool
    recorded: bool
    job_status: str | None


class BaselineProfileStore(ProfileWriter, ProfileSnapshotReader, Protocol):
    """The profile store a baseline needs: it snapshots, and reads its snapshot back."""


class BaselineStore(Protocol):
    def create(
        self, *, session_id: str, protocol: BaselineProtocol, now: datetime
    ) -> BaselineSessionRecord:
        """Opens a session, or returns the one already open. Never opens a second."""
        ...

    def open_session(self) -> BaselineSessionRecord | None: ...

    def latest_completed(self) -> BaselineSessionRecord | None: ...

    def completed_sessions(self) -> list[BaselineSessionRecord]: ...

    def items(self, session_id: str) -> list[BaselineItemRecord]: ...

    def complete(self, session_id: str, *, completed_at: datetime) -> bool:
        """Closes an open session. False when it was already closed."""
        ...

    def reopen(self, session_id: str) -> bool:
        """Undoes a `complete` when no other session is open. False when it did not reopen."""
        ...

    def save_scores(self, session_id: str, scores: Sequence[SkillScore]) -> None: ...

    def scores(self, session_id: str) -> tuple[SkillScore, ...]: ...
