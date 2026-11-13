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
    if not jobs.analyzed(session_id):
        raise SessionNotAnalyzed("The session has no finished analysis yet.")
    now = clock.now()
    # Claim before any work: the check and the close are one guarded UPDATE, so of two concurrent
    # calls only one reads the ladder and advances it.
    if not sessions_writer.claim(session_id, now):
        done = sessions_writer.completed_at(session_id)
        if done is None:
            raise SessionNotFound("No such session.")
        return CompletedSession(session_id=session_id, completed_at=done, already_completed=True)

    try:
        profile = rebuild_profile(
            observations=all_observations,
            profiles=profiles,
            taxonomy=taxonomy,
            pack=pack,
            clock=clock,
            session_id=session_id,
            reason="daily",
        )
        checked = {row.observation.error_key for row in observations.for_session(session_id)}
        rechecks.save(
            advance_rechecks(profile=profile, previous=rechecks.load(), checked=checked, now=now)
        )
    except BaseException:
        # The snapshot or the ladder failed: the session must stay open for a retry.
        sessions_writer.reopen(session_id, now)
        raise
    return CompletedSession(session_id=session_id, completed_at=now, already_completed=False)
