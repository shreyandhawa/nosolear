from datetime import date, timedelta

from factories import NOW, TAX
from hypothesis import given
from hypothesis import strategies as st

from nosolear.domain.daily_plan import (
    PLAN_STEPS,
    PromptCandidate,
    assemble_plan,
    choose_prompt,
)
from nosolear.domain.selection import (
    SKILL_ORDER,
    Focus,
    RecheckProbe,
    Selection,
)
from nosolear.domain.status import Status
from nosolear.domain.taxonomy import Skill

ALL_KEYS = tuple(d.key for d in TAX.defined())
PROMPT_IDS = tuple(f"p{i}" for i in range(8))


def keys_of(skill: Skill) -> tuple[str, ...]:
    return tuple(d.key for d in TAX.defined() if d.skill is skill)


def focus_for(key: str) -> Focus:
    definition = TAX.get(key)
    return Focus(
        skill=definition.skill,
        error_key=key,
        impact=definition.impact,
        status=Status.ACTIVE,
        p_hat=0.3,
        sampled_rate=0.3,
        score=0.9,
        runner_up_score=None,
        provisional=False,
        source="profile",
    )


@st.composite
def selections(draw: st.DrawFn) -> Selection:
    foci: list[Focus] = []
    for skill in SKILL_ORDER:
        if draw(st.booleans()):
            foci.append(focus_for(draw(st.sampled_from(keys_of(skill)))))
    probe: RecheckProbe | None = None
    if draw(st.booleans()):
        key = draw(st.sampled_from(ALL_KEYS))
        probe = RecheckProbe(
            skill=TAX.get(key).skill, error_key=key, due_at=NOW - timedelta(days=1)
        )
    return Selection(foci=tuple(foci), probe=probe)


@st.composite
def prompt_banks(draw: st.DrawFn) -> list[PromptCandidate]:
    count = draw(st.integers(min_value=0, max_value=len(PROMPT_IDS)))
    return [
        PromptCandidate(
            id=PROMPT_IDS[i],
            text=f"Prompt {i}",
            target_keys=tuple(draw(st.lists(st.sampled_from(ALL_KEYS), max_size=4, unique=True))),
        )
        for i in range(count)
    ]


recent_lists = st.lists(st.sampled_from((*PROMPT_IDS, "missing")), max_size=6)
dates = st.dates(min_value=date(2026, 1, 1), max_value=date(2030, 12, 31))


@given(day=dates, selection=selections(), bank=prompt_banks(), recent=recent_lists)
def test_caps(
    day: date,
    selection: Selection,
    bank: list[PromptCandidate],
    recent: list[str],
) -> None:
    plan = assemble_plan(
        for_date=day,
        selection=selection,
        prompts=bank,
        recent_prompt_ids=recent,
        taxonomy=TAX,
    )
    assert len(plan.foci) <= 3
    assert len(plan.drills) == len(plan.foci)
    assert [d.error_key for d in plan.drills] == [f.error_key for f in plan.foci]
    assert plan.probe == selection.probe
    assert plan.steps == PLAN_STEPS


@given(day=dates, selection=selections(), bank=prompt_banks(), recent=recent_lists)
def test_prompt_comes_from_the_bank(
    day: date,
    selection: Selection,
    bank: list[PromptCandidate],
    recent: list[str],
) -> None:
    plan = assemble_plan(
        for_date=day,
        selection=selection,
        prompts=bank,
        recent_prompt_ids=recent,
        taxonomy=TAX,
    )
    if not bank:
        assert plan.prompt is None
    else:
        assert plan.prompt in bank


@given(day=dates, selection=selections(), bank=prompt_banks(), recent=recent_lists)
def test_recent_prompt_is_avoided_when_another_exists(
    day: date,
    selection: Selection,
    bank: list[PromptCandidate],
    recent: list[str],
) -> None:
    chosen = choose_prompt(bank, selection, seed=0, recent_ids=recent)
    fresh = [c for c in bank if c.id not in set(recent)]
    if fresh and chosen is not None:
        assert chosen.id not in set(recent)


@given(day=dates, selection=selections(), bank=prompt_banks(), recent=recent_lists)
def test_assemble_is_deterministic(
    day: date,
    selection: Selection,
    bank: list[PromptCandidate],
    recent: list[str],
) -> None:
    first = assemble_plan(
        for_date=day,
        selection=selection,
        prompts=bank,
        recent_prompt_ids=recent,
        taxonomy=TAX,
    )
    again = assemble_plan(
        for_date=day,
        selection=selection,
        prompts=bank,
        recent_prompt_ids=list(reversed(recent)),
        taxonomy=TAX,
    )
    assert first == again
