"""complete_daily_session: close a daily session once, snapshot its profile and advance re-checks.

A second call changes nothing. Without that guard a retried request would advance the re-check
ladder twice for one practice session.
"""

from dataclasses import dataclass
from datetime import datetime

from nosolear.app.rebuild_profile import rebuild_profile
from nosolear.domain.feedback import SessionNotAnalyzed, SessionNotDaily, SessionNotFound
from nosolear.domain.packs import LanguagePack
from nosolear.domain.rechecks import advance_rechecks
from nosolear.domain.taxonomy import Taxonomy
from nosolear.ports.clock import Clock
from nosolear.ports.feedback import SessionJobStatus, SessionObservationReader, SessionReader
from nosolear.ports.plan import RecheckStore
from nosolear.ports.stores import ObservationReader, ProfileWriter, SessionCompleter


@dataclass(frozen=True, slots=True)
class CompletedSession:
    session_id: str
    completed_at: datetime
    already_completed: bool


def complete_daily_session(
    *,
    session_id: str,
    sessions: SessionReader,
    sessions_writer: SessionCompleter,
    jobs: SessionJobStatus,
    observations: SessionObservationReader,
    all_observations: ObservationReader,
    profiles: ProfileWriter,
    rechecks: RecheckStore,
    taxonomy: Taxonomy,
    pack: LanguagePack,
    clock: Clock,
) -> CompletedSession:
    kind = sessions.kind(session_id)
    if kind is None:
        raise SessionNotFound("No such session.")
    if kind != "daily":
        raise SessionNotDaily("Feedback is only made for a daily session.")
    if jobs.unfinished(session_id) > 0:
        raise SessionNotAnalyzed("The session is still being analyzed.")
    done = sessions_writer.completed_at(session_id)
    if done is not None:
        return CompletedSession(session_id=session_id, completed_at=done, already_completed=True)

    profile = rebuild_profile(
        observations=all_observations,
        profiles=profiles,
        taxonomy=taxonomy,
        pack=pack,
        clock=clock,
        session_id=session_id,
        reason="daily",
    )
    now = clock.now()
    checked = {row.observation.error_key for row in observations.for_session(session_id)}
    rechecks.save(
        advance_rechecks(profile=profile, previous=rechecks.load(), checked=checked, now=now)
    )
    sessions_writer.complete(session_id, now)
    return CompletedSession(session_id=session_id, completed_at=now, already_completed=False)
