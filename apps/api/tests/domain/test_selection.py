from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta

import pytest
from factories import NOW, PACK, TAX, entry, profile_of
from nosolear.domain.profile import Profile
from nosolear.domain.rechecks import RecheckState
from nosolear.domain.selection import (
    DEFAULT_SELECTION,
    SKILL_ORDER,
    Selection,
    seed_for_date,
    select,
)
from nosolear.domain.status import Status
from nosolear.domain.taxonomy import Skill

HIGH = "sound.sub.v.w"  # impact 3
LOW_IMPACT = "sound.sub.ð.d"  # impact 1
SECOND_SOUND = "sound.sub.θ.t"  # impact 2


def always_scored(key: str) -> bool:
    return True



def run(
    profile: Profile | None,
    *,
    seed: int = 0,
    now: datetime = NOW,
    history: Mapping[Skill, Sequence[str]] | None = None,
    rechecks: Mapping[str, RecheckState] | None = None,
    is_scored: Callable[[str], bool] = always_scored,
) -> Selection:
    return select(
        profile=profile,
        taxonomy=TAX,
        pack=PACK,
        seed=seed,
        now=now,
        history=history or {},
        rechecks=rechecks or {},
        is_scored=is_scored,
    )


def test_seed_for_date_is_stable_and_distinct() -> None:
    assert seed_for_date(date(2026, 11, 12)) == 13905967005293656034
    assert seed_for_date(date(2026, 11, 13)) != seed_for_date(date(2026, 11, 12))


def test_confident_high_impact_wins_most_days() -> None:
    profile = profile_of(
        [
            entry(HIGH, a=10, b=20, status=Status.ACTIVE),
            entry(LOW_IMPACT, a=6, b=2, status=Status.ACTIVE),
        ]
    )
    wins = {HIGH: 0, LOW_IMPACT: 0}
    for seed in range(200):
        sound = next(f for f in run(profile, seed=seed).foci if f.skill is Skill.SOUNDS)
        wins[sound.error_key] += 1
    assert wins[HIGH] > 120
    assert wins[LOW_IMPACT] >= 1


def test_one_focus_per_skill_in_skill_order() -> None:
    profile = profile_of(
        [
            entry(HIGH, a=10, b=20, status=Status.ACTIVE),
            entry("fluency.filler", a=10, b=20, status=Status.ACTIVE),
            entry("clarity.vague", a=10, b=20, status=Status.ACTIVE),
        ]
    )
    foci = run(profile).foci
    assert [f.skill for f in foci] == list(SKILL_ORDER)
    assert [f.error_key for f in foci] == [HIGH, "fluency.filler", "clarity.vague"]


def test_mastered_and_watching_are_never_focus() -> None:
    profile = profile_of(
        [
            entry(HIGH, a=2, b=80, status=Status.MASTERED),
            entry(SECOND_SOUND, a=3, b=20, status=Status.WATCHING),
        ]
    )
    sounds = next(f for f in run(profile).foci if f.skill is Skill.SOUNDS)
    assert sounds.error_key not in {HIGH, SECOND_SOUND}
    assert sounds.source == "fallback"


def test_due_mastered_key_is_probe_not_focus() -> None:
    profile = profile_of([entry(HIGH, a=2, b=80, status=Status.MASTERED)])
    rechecks = {HIGH: RecheckState(stage=0, next_at=NOW - timedelta(days=1))}
    selection = run(profile, rechecks=rechecks)
    assert selection.probe is not None
    assert selection.probe.error_key == HIGH
    assert selection.probe.skill is Skill.SOUNDS
    assert selection.probe.due_at == NOW - timedelta(days=1)
    assert HIGH not in {f.error_key for f in selection.foci}


def test_not_yet_due_mastered_key_is_not_probe() -> None:
    profile = profile_of([entry(HIGH, a=2, b=80, status=Status.MASTERED)])
    rechecks = {HIGH: RecheckState(stage=0, next_at=NOW + timedelta(days=1))}
    assert run(profile, rechecks=rechecks).probe is None


def test_unscored_key_is_never_selected() -> None:
    profile = profile_of(
        [
            entry(HIGH, a=40, b=60, status=Status.ACTIVE),
            entry(SECOND_SOUND, a=2, b=20, status=Status.ACTIVE),
        ]
    )
    rechecks = {HIGH: RecheckState(stage=0, next_at=NOW - timedelta(days=1))}

    def is_scored(key: str) -> bool:
        return key != HIGH

    for seed in range(50):
        selection = run(profile, seed=seed, rechecks=rechecks, is_scored=is_scored)
        assert HIGH not in {f.error_key for f in selection.foci}
        assert selection.probe is None


def test_streak_of_three_blocks_winner_unless_double() -> None:
    # The winner without history, and the runner-up's score.
    profile = profile_of(
        [
            entry(HIGH, a=90, b=2, status=Status.ACTIVE),
            entry(LOW_IMPACT, a=2, b=90, status=Status.ACTIVE),
        ]
    )
    free = next(f for f in run(profile).foci if f.skill is Skill.SOUNDS)
    streak = {Skill.SOUNDS: [free.error_key] * 3}
    blocked = next(f for f in run(profile, history=streak).foci if f.skill is Skill.SOUNDS)
    assert free.runner_up_score is not None
    assert free.score >= 2 * free.runner_up_score
    assert blocked.error_key == free.error_key

    close = profile_of(
        [
            entry(HIGH, a=10, b=20, status=Status.ACTIVE),
            entry(SECOND_SOUND, a=10, b=20, status=Status.ACTIVE),
        ]
    )
    seen_block = False
    for seed in range(100):
        free = next(f for f in run(close, seed=seed).foci if f.skill is Skill.SOUNDS)
        streak = {Skill.SOUNDS: [free.error_key] * 3}
        forced = next(
            f for f in run(close, seed=seed, history=streak).foci if f.skill is Skill.SOUNDS
        )
        assert free.runner_up_score is not None
        if free.score < 2 * free.runner_up_score:
            assert forced.error_key != free.error_key
            seen_block = True
        else:
            assert forced.error_key == free.error_key
    assert seen_block


def test_empty_profile_still_has_one_focus_per_skill() -> None:
    selection = run(None)
    assert [f.skill for f in selection.foci] == list(SKILL_ORDER)
    for focus in selection.foci:
        assert focus.source == "fallback"
        assert focus.status is Status.UNKNOWN
        assert focus.provisional is False
        assert TAX.get(focus.error_key).skill is focus.skill
    assert selection.probe is None


def test_naive_now_is_rejected() -> None:
    with pytest.raises(ValueError):
        run(None, now=datetime(2026, 11, 12, 8, 0))  # noqa: DTZ001


def test_provisional_flag_is_carried() -> None:
    profile = profile_of([entry(HIGH, a=40, b=60, status=Status.ACTIVE, provisional=True)])
    sounds = next(f for f in run(profile).foci if f.skill is Skill.SOUNDS)
    assert sounds.error_key == HIGH
    assert sounds.provisional is True
    assert sounds.source == "profile"


def test_fallback_uses_the_pack_prior_and_taxonomy_keys() -> None:
    selection = run(None)
    for focus in selection.foci:
        prior = PACK.prior_for(focus.error_key)
        assert focus.p_hat == pytest.approx(prior.a0 / (prior.a0 + prior.b0))
        assert focus.impact == TAX.get(focus.error_key).impact


def test_default_selection_matches_the_spec() -> None:
    assert DEFAULT_SELECTION.max_streak == 3
    assert DEFAULT_SELECTION.streak_ratio == 2.0
    assert DEFAULT_SELECTION.focus_statuses == {Status.ACTIVE, Status.IMPROVING, Status.UNKNOWN}


def test_aware_utc_now_is_accepted() -> None:
    assert run(None, now=datetime(2026, 11, 12, 8, 0, tzinfo=UTC)).foci
