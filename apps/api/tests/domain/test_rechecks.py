from datetime import timedelta

import pytest
from factories import NOW, entry, profile_of
from hypothesis import given
from hypothesis import strategies as st

from nosolear.domain.profile import Profile
from nosolear.domain.rechecks import RECHECK_DAYS, RecheckState, advance_rechecks
from nosolear.domain.status import Status

KEY = "sound.sub.v.w"


def mastered(*keys: str) -> Profile:
    return profile_of(entry(k, a=2, b=80, status=Status.MASTERED) for k in keys)


def test_recheck_days_are_the_spec_values() -> None:
    assert RECHECK_DAYS == (2, 4, 8, 16, 32)


def test_newly_mastered_starts_at_two_days() -> None:
    states = advance_rechecks(profile=mastered(KEY), previous={}, checked=set(), now=NOW)
    assert states == {KEY: RecheckState(stage=0, next_at=NOW + timedelta(days=2))}


def test_checked_key_advances_through_2_4_8_16_32_then_stays_at_32() -> None:
    profile = mastered(KEY)
    state = advance_rechecks(profile=profile, previous={}, checked=set(), now=NOW)[KEY]
    gaps = [state.next_at - NOW]
    for _ in range(6):
        now = state.next_at
        state = advance_rechecks(profile=profile, previous={KEY: state}, checked={KEY}, now=now)[
            KEY
        ]
        gaps.append(state.next_at - now)
    assert [g.days for g in gaps] == [2, 4, 8, 16, 32, 32, 32]
    assert state.stage == 4


def test_unchecked_key_keeps_state() -> None:
    previous = {KEY: RecheckState(stage=2, next_at=NOW - timedelta(days=3))}
    states = advance_rechecks(profile=mastered(KEY), previous=previous, checked=set(), now=NOW)
    assert states == previous


def test_checked_key_that_is_not_yet_due_keeps_its_rung() -> None:
    """Practised early is not a re-check: the ladder moves only when the check is due."""
    previous = {KEY: RecheckState(stage=1, next_at=NOW + timedelta(days=3))}
    states = advance_rechecks(profile=mastered(KEY), previous=previous, checked={KEY}, now=NOW)
    assert states == previous


def test_five_daily_sessions_do_not_race_a_key_up_the_ladder() -> None:
    """A key checked every day moves only when each re-check falls due: 2 days, then 4 more. The
    old rule reached the 32-day rung in five sessions."""
    profile = mastered(KEY)
    states = advance_rechecks(profile=profile, previous={}, checked=set(), now=NOW)
    for day in range(1, 6):
        now = NOW + timedelta(days=day)
        states = advance_rechecks(profile=profile, previous=states, checked={KEY}, now=now)
    assert states[KEY].stage == 1
    assert states[KEY].next_at == NOW + timedelta(days=2 + 4)


def test_relapsed_key_is_dropped_and_restarts_at_stage_zero() -> None:
    previous = {KEY: RecheckState(stage=3, next_at=NOW + timedelta(days=5))}
    relapsed = profile_of([entry(KEY, a=40, b=60, status=Status.ACTIVE)])
    assert advance_rechecks(profile=relapsed, previous=previous, checked={KEY}, now=NOW) == {}
    again = advance_rechecks(profile=mastered(KEY), previous={}, checked=set(), now=NOW)
    assert again[KEY].stage == 0


def test_naive_now_is_rejected() -> None:
    with pytest.raises(ValueError):
        advance_rechecks(
            profile=mastered(KEY),
            previous={},
            checked=set(),
            now=NOW.replace(tzinfo=None),
        )


@given(
    stage=st.integers(min_value=0, max_value=4),
    offset_hours=st.integers(min_value=-2000, max_value=2000),
    checked=st.booleans(),
    is_mastered=st.booleans(),
)
def test_next_at_is_always_in_the_future_of_now_and_stage_is_bounded(
    stage: int, offset_hours: int, checked: bool, is_mastered: bool
) -> None:
    now = NOW + timedelta(hours=offset_hours)
    status = Status.MASTERED if is_mastered else Status.ACTIVE
    profile = profile_of([entry(KEY, a=2, b=80, status=status)])
    previous = {KEY: RecheckState(stage=stage, next_at=NOW)}
    states = advance_rechecks(
        profile=profile, previous=previous, checked={KEY} if checked else set(), now=now
    )
    if not is_mastered:
        assert states == {}
        return
    state = states[KEY]
    assert 0 <= state.stage <= 4
    if checked:
        assert state.next_at > now
    else:
        assert state == previous[KEY]
