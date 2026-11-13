"""The re-check schedule for mastered keys (ARCHITECTURE §6.7).

A mastered key is re-checked on a fixed ladder. Each check that finds it again moves it one rung
up, so a key that keeps passing is looked at less and less often, and a key that stops being
mastered leaves the schedule and restarts at the bottom when it is mastered again.
"""

from collections.abc import Mapping, Set
from dataclasses import dataclass
from datetime import datetime, timedelta

from nosolear.domain.profile import Profile
from nosolear.domain.status import Status

RECHECK_DAYS: tuple[int, ...] = (2, 4, 8, 16, 32)
_TOP_STAGE = len(RECHECK_DAYS) - 1


@dataclass(frozen=True, slots=True)
class RecheckState:
    stage: int
    next_at: datetime


def advance_rechecks(
    *,
    profile: Profile,
    previous: Mapping[str, RecheckState],
    checked: Set[str],
    now: datetime,
) -> dict[str, RecheckState]:
    """The schedule after one session.

    `checked` holds the mastered keys that had at least one opportunity in the session just
    completed. A key with no opportunity keeps its state, so a key the learner did not practise
    is not moved along the ladder by a session that never tested it. Only the clock passed in
    is read, so the result is a function of its arguments.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    result: dict[str, RecheckState] = {}
    for entry in profile.entries:
        if entry.status is not Status.MASTERED:
            continue
        key = entry.definition.key
        prior = previous.get(key)
        if prior is None:
            stage = 0
        elif key in checked:
            stage = min(prior.stage + 1, _TOP_STAGE)
        else:
            result[key] = prior
            continue
        result[key] = RecheckState(stage=stage, next_at=now + timedelta(days=RECHECK_DAYS[stage]))
    return result
