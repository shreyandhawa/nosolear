"""Ports for feedback: the observations of one session and the stored feedback items.

Adapters: `persistence`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, get_args

from nosolear.domain.observations import Observation
from nosolear.domain.taxonomy import Skill

if TYPE_CHECKING:
    # Imported for annotations only: domain/feedback.py imports StoredObservation from here.
    from nosolear.domain.feedback import SkillState

FallbackReason = Literal[
    "cap_exceeded", "provider_unavailable", "capability_missing", "invalid_output"
]
FALLBACK_REASONS: tuple[str, ...] = get_args(FallbackReason)
FeedbackSource = Literal["coach", "template"]
FEEDBACK_SOURCES: tuple[str, ...] = get_args(FeedbackSource)


@dataclass(frozen=True, slots=True)
class StoredObservation:
    """A stored observation with its row id, so feedback can point back at its evidence."""

    id: int
    observation: Observation


class SessionReader(Protocol):
    def kind(self, session_id: str) -> str | None:
        """The session's kind, or None when there is no such session."""
        ...


class SessionJobStatus(Protocol):
    def analyzed(self, session_id: str) -> bool:
        """True once the session's recording has been analysed: an analyze job of its attempts has
        ended (done or failed), and no job of its attempts is still queued or running. A session
        with no upload, or only a queued job, is not analysed."""
        ...


class SessionObservationReader(Protocol):
    def for_session(self, session_id: str) -> list[StoredObservation]: ...


@dataclass(frozen=True, slots=True)
class FeedbackItem:
    id: str
    session_id: str
    skill: Skill
    error_key: str
    observation_id: int
    attempt_id: str | None
    start_ms: int | None
    end_ms: int | None
    word: str | None
    message: str
    model_text: str | None
    source: FeedbackSource
    fallback_reason: FallbackReason | None


class FeedbackStore(Protocol):
    def for_session(self, session_id: str) -> list[FeedbackItem]: ...

    def upsert(self, session_id: str, items: Sequence[FeedbackItem]) -> None:
        """Replaces the stored item for each (session, skill) pair in `items`."""
        ...


@dataclass(frozen=True, slots=True)
class SkillFeedback:
    skill: Skill
    state: SkillState
    item: FeedbackItem | None


@dataclass(frozen=True, slots=True)
class FeedbackReport:
    session_id: str
    skills: tuple[SkillFeedback, ...]
    degraded: bool
