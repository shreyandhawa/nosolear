from datetime import date, timedelta

from factories import NOW, TAX

from nosolear.domain.daily_plan import (
    PLAN_PROTOCOL_VERSION,
    PLAN_STEPS,
    PlanStep,
    PromptCandidate,
    StepKind,
    assemble_plan,
    choose_prompt,
)
from nosolear.domain.selection import Focus, RecheckProbe, Selection, seed_for_date
from nosolear.domain.status import Status
from nosolear.domain.taxonomy import Skill

SOUND = "sound.sub.v.w"
SOUND_2 = "sound.sub.ʃ.s"
FLUENCY = "fluency.filler"
CLARITY = "clarity.vague"
DAY = date(2026, 11, 12)


def focus(key: str) -> Focus:
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


def selection(*keys: str, probe: str | None = None) -> Selection:
    probe_record = (
        RecheckProbe(skill=TAX.get(probe).skill, error_key=probe, due_at=NOW - timedelta(days=1))
        if probe is not None
        else None
    )
    return Selection(foci=tuple(focus(k) for k in keys), probe=probe_record)


def prompt(id_: str, *targets: str) -> PromptCandidate:
    return PromptCandidate(id=id_, text=f"Say something about {id_}.", target_keys=targets)


def test_prompt_with_most_focus_keys_wins() -> None:
    sel = selection(SOUND, FLUENCY)
    both = prompt("both", SOUND, FLUENCY)
    one = prompt("one", SOUND)
    chosen = choose_prompt([one, both], sel, seed=1)
    assert chosen == both


def test_probe_key_adds_half_weight() -> None:
    sel = selection(SOUND, probe=CLARITY)
    probe_only = prompt("probe", CLARITY)
    nothing = prompt("nothing")
    assert choose_prompt([nothing, probe_only], sel, seed=3) == probe_only
    focus_prompt = prompt("focus", SOUND)
    assert choose_prompt([probe_only, focus_prompt], sel, seed=3) == focus_prompt


def test_recent_prompts_are_avoided_when_alternatives_exist() -> None:
    sel = selection(SOUND)
    best = prompt("best", SOUND)
    other = prompt("other")
    chosen = choose_prompt([best, other], sel, seed=5, recent_ids=["best"])
    assert chosen == other


def test_recent_prompts_allowed_when_only_choice() -> None:
    sel = selection(SOUND)
    only = prompt("only", SOUND)
    assert choose_prompt([only], sel, seed=5, recent_ids=["only"]) == only


def test_empty_prompt_bank_gives_no_prompt() -> None:
    assert choose_prompt([], selection(SOUND), seed=0) is None


def test_steps_match_protocol_times() -> None:
    assert (
        PlanStep(StepKind.SPEAK, None, 60),
        PlanStep(StepKind.ANALYZE, None, 45),
        PlanStep(StepKind.FEEDBACK, None, 90),
        PlanStep(StepKind.DRILL, Skill.SOUNDS, 240),
        PlanStep(StepKind.DRILL, Skill.ON_THE_SPOT, 180),
        PlanStep(StepKind.DRILL, Skill.ARTICULATE, 180),
        PlanStep(StepKind.LOG, None, 0),
    ) == PLAN_STEPS
    assert sum(step.duration_s for step in PLAN_STEPS) == 60 + 45 + 90 + 240 + 180 + 180


def test_drills_follow_focus_and_use_taxonomy_drill_family() -> None:
    plan = assemble_plan(
        for_date=DAY,
        selection=selection(SOUND, FLUENCY, CLARITY),
        prompts=[],
        recent_prompt_ids=[],
        taxonomy=TAX,
    )
    assert [(d.skill, d.error_key, d.drill_family) for d in plan.drills] == [
        (Skill.SOUNDS, SOUND, "minimal_pairs"),
        (Skill.ON_THE_SPOT, FLUENCY, "rapid_questions"),
        (Skill.ARTICULATE, CLARITY, "clarity_rewrite"),
    ]


def test_plan_for_same_date_is_identical() -> None:
    sel = selection(SOUND, FLUENCY, probe=CLARITY)
    prompts = [prompt("a", SOUND), prompt("b", FLUENCY), prompt("c", CLARITY)]
    first = assemble_plan(
        for_date=DAY, selection=sel, prompts=prompts, recent_prompt_ids=["a"], taxonomy=TAX
    )
    second = assemble_plan(
        for_date=DAY, selection=sel, prompts=prompts, recent_prompt_ids=["a"], taxonomy=TAX
    )
    assert first == second
    assert first.seed == seed_for_date(DAY)
    assert first.protocol_version == PLAN_PROTOCOL_VERSION
    assert first.steps == PLAN_STEPS
    assert first.probe is not None
    assert first.for_date == DAY


def test_empty_profile_plan_has_no_prompt_when_bank_is_empty() -> None:
    plan = assemble_plan(
        for_date=DAY,
        selection=selection(SOUND_2, FLUENCY, CLARITY),
        prompts=[],
        recent_prompt_ids=[],
        taxonomy=TAX,
    )
    assert plan.prompt is None
    assert len(plan.drills) == 3
