"""Assemble one day's plan from its selection: the prompt, the drills and the fixed step sequence.

Pure: the date comes in as an argument and the seed is derived from it, so the same date always
gives the same plan. The step times are the protocol of ARCHITECTURE §8.2.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from random import Random

from nosolear.domain.selection import Focus, RecheckProbe, Selection, seed_for_date
from nosolear.domain.taxonomy import Skill, Taxonomy

PLAN_PROTOCOL_VERSION = 1
_PROBE_WEIGHT = 0.5


class StepKind(StrEnum):
    SPEAK = "speak"
    ANALYZE = "analyze"
    FEEDBACK = "feedback"
    DRILL = "drill"
    LOG = "log"


@dataclass(frozen=True, slots=True)
class PlanStep:
    kind: StepKind
    skill: Skill | None
    duration_s: int


PLAN_STEPS: tuple[PlanStep, ...] = (
    PlanStep(StepKind.SPEAK, None, 60),
    PlanStep(StepKind.ANALYZE, None, 45),
    PlanStep(StepKind.FEEDBACK, None, 90),
    PlanStep(StepKind.DRILL, Skill.SOUNDS, 240),
    PlanStep(StepKind.DRILL, Skill.ON_THE_SPOT, 180),
    PlanStep(StepKind.DRILL, Skill.ARTICULATE, 180),
    PlanStep(StepKind.LOG, None, 0),
)


@dataclass(frozen=True, slots=True)
class PromptCandidate:
    id: str
    text: str
    target_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DrillSpec:
    skill: Skill
    error_key: str
    drill_family: str


@dataclass(frozen=True, slots=True)
class DailyPlan:
    for_date: date
    seed: int
    foci: tuple[Focus, ...]
    probe: RecheckProbe | None
    prompt: PromptCandidate | None
    drills: tuple[DrillSpec, ...]
    steps: tuple[PlanStep, ...]
    protocol_version: int


def _density(candidate: PromptCandidate, selection: Selection) -> float:
    """How many of today's focus keys the prompt targets, plus half a point for the probe key."""
    targets = set(candidate.target_keys)
    density = float(sum(1 for f in selection.foci if f.error_key in targets))
    if selection.probe is not None and selection.probe.error_key in targets:
        density += _PROBE_WEIGHT
    return density


def choose_prompt(
    candidates: Sequence[PromptCandidate],
    selection: Selection,
    *,
    seed: int,
    recent_ids: Sequence[str] = (),
) -> PromptCandidate | None:
    """The prompt that targets the most of today's keys.

    Prompts used recently are skipped while any other prompt is available, so the learner is not
    shown the same one again. Ties, including the case where no prompt targets a key, are broken
    by a generator seeded from the date over the sorted ids, so the choice is deterministic.
    """
    if not candidates:
        return None
    recent = set(recent_ids)
    pool = [c for c in candidates if c.id not in recent] or list(candidates)
    best = max(_density(c, selection) for c in pool)
    tied = sorted((c for c in pool if _density(c, selection) == best), key=lambda c: c.id)
    return Random(seed).choice(tied)


def assemble_plan(
    *,
    for_date: date,
    selection: Selection,
    prompts: Sequence[PromptCandidate],
    recent_prompt_ids: Sequence[str],
    taxonomy: Taxonomy,
) -> DailyPlan:
    """One drill per focus, at most one probe, one prompt and the fixed protocol steps."""
    seed = seed_for_date(for_date)
    drills = tuple(
        DrillSpec(
            skill=f.skill,
            error_key=f.error_key,
            drill_family=taxonomy.get(f.error_key).drill_family,
        )
        for f in selection.foci
    )
    return DailyPlan(
        for_date=for_date,
        seed=seed,
        foci=selection.foci,
        probe=selection.probe,
        prompt=choose_prompt(prompts, selection, seed=seed, recent_ids=recent_prompt_ids),
        drills=drills,
        steps=PLAN_STEPS,
        protocol_version=PLAN_PROTOCOL_VERSION,
    )
