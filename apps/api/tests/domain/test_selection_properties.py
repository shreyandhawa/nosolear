from collections.abc import Mapping, Sequence
from datetime import date, timedelta

from factories import NOW, PACK, TAX, entry, profile_of
from hypothesis import given
from hypothesis import strategies as st

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

ALL_KEYS = tuple(d.key for d in TAX.defined())
FOCUS_STATUSES = DEFAULT_SELECTION.focus_statuses

seeds = st.integers(min_value=0, max_value=2**64 - 1)
statuses = st.sampled_from(tuple(Status))
keys = st.sampled_from(ALL_KEYS)
unscored_sets = st.frozensets(keys, max_size=6)
recheck_maps = st.dictionaries(
    keys,
    st.builds(
        RecheckState,
        stage=st.integers(min_value=0, max_value=4),
        next_at=st.integers(min_value=-1000, max_value=1000).map(
            lambda h: NOW + timedelta(hours=h)
        ),
    ),
    max_size=6,
)
skill_history = st.one_of(
    st.lists(keys, max_size=5),
    keys.map(lambda k: [k] * 4),
)
histories = st.fixed_dictionaries({skill: skill_history for skill in SKILL_ORDER})


@st.composite
def profiles(draw: st.DrawFn) -> Profile:
    """Random profiles. Often one whole skill is profiled as watching or mastered, the case where
    the focus has to fall back past the focus statuses (random draws rarely reach it)."""
    chosen = draw(st.lists(keys, max_size=12, unique=True))
    cover = draw(st.one_of(st.none(), st.sampled_from(SKILL_ORDER)))
    if cover is not None:
        chosen = list(dict.fromkeys([*chosen, *(d.key for d in TAX.defined() if d.skill is cover)]))
    entries = []
    for key in chosen:
        if cover is not None and TAX.get(key).skill is cover:
            status = draw(st.sampled_from((Status.WATCHING, Status.MASTERED)))
        else:
            status = draw(statuses)
        entries.append(
            entry(
                key,
                a=draw(st.floats(min_value=1.0, max_value=80.0)),
                b=draw(st.floats(min_value=1.0, max_value=80.0)),
                status=status,
                provisional=draw(st.booleans()),
            )
        )
    return profile_of(entries)


def _select(
    profile: Profile,
    *,
    seed: int,
    history: Mapping[Skill, Sequence[str]],
    rechecks: Mapping[str, RecheckState],
    unscored: frozenset[str],
) -> Selection:
    def is_scored(key: str) -> bool:
        return key not in unscored

    return select(
        profile=profile,
        taxonomy=TAX,
        pack=PACK,
        seed=seed,
        now=NOW,
        history=history,
        rechecks=rechecks,
        is_scored=is_scored,
    )


@given(
    profile=profiles(),
    seed=seeds,
    history=histories,
    rechecks=recheck_maps,
    unscored=unscored_sets,
    data=st.data(),
)
def test_determinism_and_entry_order_independence(
    profile: Profile,
    seed: int,
    history: Mapping[Skill, Sequence[str]],
    rechecks: Mapping[str, RecheckState],
    unscored: frozenset[str],
    data: st.DataObject,
) -> None:
    first = _select(profile, seed=seed, history=history, rechecks=rechecks, unscored=unscored)
    again = _select(profile, seed=seed, history=history, rechecks=rechecks, unscored=unscored)
    assert first == again
    shuffled = profile_of(data.draw(st.permutations(profile.entries)))
    assert (
        _select(shuffled, seed=seed, history=history, rechecks=rechecks, unscored=unscored) == first
    )


@given(
    profile=profiles(),
    seed=seeds,
    history=histories,
    rechecks=recheck_maps,
    unscored=unscored_sets,
)
def test_exactly_one_focus_per_skill_with_any_scored_key(
    profile: Profile,
    seed: int,
    history: Mapping[Skill, Sequence[str]],
    rechecks: Mapping[str, RecheckState],
    unscored: frozenset[str],
) -> None:
    """ARCHITECTURE 6.6: one focus per skill. A skill with any scored key gets exactly one, even
    when every key it has is watching or mastered, so the plan never goes without a drill."""
    selection = _select(profile, seed=seed, history=history, rechecks=rechecks, unscored=unscored)
    skills = [f.skill for f in selection.foci]
    assert len(set(skills)) == len(skills)
    assert skills == sorted(skills, key=SKILL_ORDER.index)
    for skill in SKILL_ORDER:
        scored = [d for d in TAX.defined() if d.skill is skill and d.key not in unscored]
        assert skills.count(skill) == (1 if scored else 0)


@given(
    profile=profiles(),
    seed=seeds,
    history=histories,
    rechecks=recheck_maps,
    unscored=unscored_sets,
)
def test_focus_is_scored_of_its_skill_and_focusable(
    profile: Profile,
    seed: int,
    history: Mapping[Skill, Sequence[str]],
    rechecks: Mapping[str, RecheckState],
    unscored: frozenset[str],
) -> None:
    selection = _select(profile, seed=seed, history=history, rechecks=rechecks, unscored=unscored)
    owned = {e.definition.key for e in profile.entries}
    for focus in selection.foci:
        assert focus.error_key not in unscored
        assert TAX.get(focus.error_key).skill is focus.skill
        if focus.source == "profile":
            assert focus.error_key in owned
        else:
            assert focus.status is Status.UNKNOWN
            assert focus.error_key not in owned


@given(
    profile=profiles(),
    seed=seeds,
    history=histories,
    rechecks=recheck_maps,
    unscored=unscored_sets,
)
def test_variety_rule_holds(
    profile: Profile,
    seed: int,
    history: Mapping[Skill, Sequence[str]],
    rechecks: Mapping[str, RecheckState],
    unscored: frozenset[str],
) -> None:
    selection = _select(profile, seed=seed, history=history, rechecks=rechecks, unscored=unscored)
    for focus in selection.foci:
        recent = history[focus.skill]
        if len(recent) < 3 or not (recent[0] == recent[1] == recent[2]):
            continue
        streak_key = recent[0]
        if focus.error_key != streak_key:
            continue
        assert focus.runner_up_score is None or focus.score >= 2 * focus.runner_up_score


@given(
    profile=profiles(),
    seed=seeds,
    history=histories,
    rechecks=recheck_maps,
    unscored=unscored_sets,
)
def test_probe_is_due_scored_mastered_and_never_a_focus(
    profile: Profile,
    seed: int,
    history: Mapping[Skill, Sequence[str]],
    rechecks: Mapping[str, RecheckState],
    unscored: frozenset[str],
) -> None:
    selection = _select(profile, seed=seed, history=history, rechecks=rechecks, unscored=unscored)
    eligible = [
        e
        for e in profile.entries
        if e.status is Status.MASTERED
        and e.definition.key in rechecks
        and rechecks[e.definition.key].next_at <= NOW
        and e.definition.key not in unscored
    ]
    if not eligible:
        assert selection.probe is None
        return
    probe = selection.probe
    assert probe is not None
    assert probe.error_key not in unscored
    assert probe.error_key not in {f.error_key for f in selection.foci}
    assert probe.due_at == rechecks[probe.error_key].next_at
    assert probe.due_at <= NOW
    assert TAX.get(probe.error_key).skill is probe.skill
    assert TAX.get(probe.error_key).impact == max(e.definition.impact for e in eligible)


def test_different_dates_vary() -> None:
    profile = profile_of(
        [
            entry("sound.sub.v.w", a=10, b=20, status=Status.ACTIVE),
            entry("sound.sub.ʃ.s", a=10, b=20, status=Status.ACTIVE),
        ]
    )
    start = date(2026, 11, 12)
    chosen: set[str] = set()
    for offset in range(50):
        day = start + timedelta(days=offset)
        selection = _select(
            profile,
            seed=seed_for_date(day),
            history={},
            rechecks={},
            unscored=frozenset(),
        )
        sounds = next(f for f in selection.foci if f.skill is Skill.SOUNDS)
        chosen.add(sounds.error_key)
    assert chosen == {"sound.sub.v.w", "sound.sub.ʃ.s"}
