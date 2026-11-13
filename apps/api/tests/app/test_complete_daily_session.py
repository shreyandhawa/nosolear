"""complete_daily_session: snapshot the profile for the session, advance the re-checks once."""

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from factories import DAY, NOW, PACK, TAX, FixedClock, mk
from fakes import (
    FakeProfileStore,
    FakeRecheckStore,
    FakeSessionCompleter,
    FakeSessionJobStatus,
    FakeSessionReader,
)

from nosolear.app.complete_daily_session import complete_daily_session
from nosolear.domain.feedback import SessionNotAnalyzed, SessionNotDaily, SessionNotFound
from nosolear.domain.observations import Observation, Outcome
from nosolear.domain.rechecks import RecheckState
from nosolear.domain.taxonomy import Detector
from nosolear.ports.feedback import StoredObservation

SESSION = "s1"
SOUND = "sound.sub.v.w"


@dataclass
class Log:
    """Every observation in the store; `session_of` says which session each one belongs to."""

    rows: list[StoredObservation]
    session_of: dict[int, str]

    def current(self) -> list[Observation]:
        return [row.observation for row in self.rows]

    def for_session(self, session_id: str) -> list[StoredObservation]:
        return [row for row in self.rows if self.session_of[row.id] == session_id]


def _log(*, ok_count: int = 0, session_key: str | None = SOUND) -> Log:
    """`ok_count` earlier successes on the sound (enough to be mastered), then one session success.
    The successes are a minute apart: 40 of them give a mastered estimate, 25 do not."""
    rows: list[StoredObservation] = []
    session_of: dict[int, str] = {}
    for index in range(ok_count):
        at = NOW - timedelta(minutes=ok_count - index)
        obs = mk(SOUND, Outcome.OK, at, detector=Detector.AZURE_PA, attempt_id="old")
        rows.append(StoredObservation(id=index + 1, observation=obs))
        session_of[index + 1] = "old"
    if session_key is not None:
        obs = mk(session_key, Outcome.OK, NOW, detector=Detector.AZURE_PA, attempt_id="a1")
        rows.append(StoredObservation(id=ok_count + 1, observation=obs))
        session_of[ok_count + 1] = SESSION
    return Log(rows=rows, session_of=session_of)


@dataclass
class World:
    sessions: FakeSessionReader
    completer: FakeSessionCompleter
    jobs: FakeSessionJobStatus
    log: Log
    profiles: FakeProfileStore
    rechecks: FakeRecheckStore


def world(*, kind: str = "daily", unfinished: int = 0, log: Log | None = None) -> World:
    return World(
        sessions=FakeSessionReader({SESSION: kind}),
        completer=FakeSessionCompleter(),
        jobs=FakeSessionJobStatus({SESSION: unfinished}),
        log=log or _log(),
        profiles=FakeProfileStore(),
        rechecks=FakeRecheckStore(),
    )


def call(w: World, *, at: datetime = NOW):
    return complete_daily_session(
        session_id=SESSION,
        sessions=w.sessions,
        sessions_writer=w.completer,
        jobs=w.jobs,
        observations=w.log,
        all_observations=w.log,
        profiles=w.profiles,
        rechecks=w.rechecks,
        taxonomy=TAX,
        pack=PACK,
        clock=FixedClock(at),
    )


def test_snapshot_has_daily_reason_and_session_id() -> None:
    w = world()
    result = call(w)
    assert result.already_completed is False
    assert result.completed_at == NOW
    assert len(w.profiles.saved) == 1
    _profile, session_id, reason = w.profiles.saved[0]
    assert session_id == SESSION
    assert reason == "daily"


def test_second_complete_is_a_noop() -> None:
    w = world(log=_log(ok_count=40))
    first = call(w)
    stored_after_first = dict(w.rechecks.states)
    snapshots_after_first = len(w.profiles.saved)

    second = call(w, at=NOW + DAY)

    assert second.already_completed is True
    assert second.completed_at == first.completed_at
    assert w.rechecks.states == stored_after_first
    assert len(w.profiles.saved) == snapshots_after_first


def test_checked_mastered_key_advances_recheck() -> None:
    w = world(log=_log(ok_count=40))
    call(w)
    state = w.rechecks.states.get(SOUND)
    assert isinstance(state, RecheckState), "a mastered key checked today must get a re-check"
    assert state.stage == 0
    assert state.next_at == NOW + timedelta(days=2)


def test_unfinished_job_refuses() -> None:
    w = world(unfinished=1)
    with pytest.raises(SessionNotAnalyzed):
        call(w)
    assert w.completer.calls == []
    assert w.profiles.saved == []


@pytest.mark.parametrize(
    ("kind", "error"),
    [("baseline", SessionNotDaily)],
)
def test_non_daily_session_refuses(kind: str, error: type[Exception]) -> None:
    w = world(kind=kind)
    with pytest.raises(error):
        call(w)
    assert w.completer.calls == []


def test_unknown_session_refuses() -> None:
    w = world()
    w.sessions = FakeSessionReader({})
    with pytest.raises(SessionNotFound):
        call(w)
