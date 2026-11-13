"""The daily plan store: exact round trip, one plan per local date, history, the prompt bank."""

from datetime import date, datetime
from typing import Any

import pytest
from factories import NOW, TAX
from sqlalchemy import Engine, insert
from sqlalchemy.exc import IntegrityError

from nosolear.domain.daily_plan import (
    PLAN_PROTOCOL_VERSION,
    PLAN_STEPS,
    DailyPlan,
    DrillSpec,
    PromptCandidate,
)
from nosolear.domain.selection import Focus, RecheckProbe, seed_for_date
from nosolear.domain.status import Status
from nosolear.domain.taxonomy import Skill
from nosolear.persistence.models import content_items, daily_plans
from nosolear.persistence.plan_repositories import (
    DailyPlanRepository,
    PromptBankRepository,
)

SOUND = "sound.sub.v.w"
SOUND_2 = "sound.sub.ʃ.s"
FLUENCY = "fluency.filler"
CLARITY = "clarity.vague"
DAY = date(2026, 11, 12)


def _focus(key: str, *, p_hat: float = 0.31, status: Status = Status.ACTIVE) -> Focus:
    definition = TAX.get(key)
    return Focus(
        skill=definition.skill,
        error_key=key,
        impact=definition.impact,
        status=status,
        p_hat=p_hat,
        sampled_rate=0.4,
        score=1.25,
        runner_up_score=None,
        provisional=False,
        source="profile",
    )


def _plan(
    day: date,
    *,
    keys: tuple[str, ...] = (SOUND, FLUENCY, CLARITY),
    prompt: PromptCandidate | None = None,
    probe: RecheckProbe | None = None,
) -> DailyPlan:
    return DailyPlan(
        for_date=day,
        seed=seed_for_date(day),
        foci=tuple(_focus(k) for k in keys),
        probe=probe,
        prompt=prompt,
        drills=tuple(
            DrillSpec(
                skill=TAX.get(k).skill,
                error_key=k,
                drill_family=TAX.get(k).drill_family,
            )
            for k in keys
        ),
        steps=PLAN_STEPS,
        protocol_version=PLAN_PROTOCOL_VERSION,
    )


def _insert_content(
    engine: Engine,
    item_id: str,
    *,
    kind: str = "prompt",
    text: str = "Tell me about your weekend.",
    keys: tuple[str, ...] = (SOUND,),
    retired_at: datetime | None = None,
) -> None:
    import json

    with engine.begin() as conn:
        conn.execute(
            insert(content_items).values(
                id=item_id,
                kind=kind,
                text=text,
                target_keys=json.dumps(list(keys)),
                source="seed",
                retired_at=retired_at,
            )
        )


def test_add_then_get_roundtrips_the_plan_exactly(db_engine: Engine) -> None:
    _insert_content(db_engine, "p-1")
    plan = _plan(
        DAY,
        prompt=PromptCandidate(id="p-1", text="Tell me about your weekend.", target_keys=(SOUND,)),
        probe=RecheckProbe(skill=Skill.SOUNDS, error_key=SOUND_2, due_at=NOW),
    )
    assert plan.seed >= 2**63  # the seed does not fit a signed 64-bit column without care
    repo = DailyPlanRepository(db_engine, TAX)

    stored = repo.add(plan)

    assert stored.plan == plan
    assert repo.get(DAY) == stored


def test_second_add_for_same_date_returns_first_plan(db_engine: Engine) -> None:
    repo = DailyPlanRepository(db_engine, TAX)
    first = repo.add(_plan(DAY, keys=(SOUND,)))

    second = repo.add(_plan(DAY, keys=(FLUENCY,)))

    assert second == first
    assert repo.get(DAY) == first


def test_recent_focus_keys_are_most_recent_first_and_per_skill(db_engine: Engine) -> None:
    repo = DailyPlanRepository(db_engine, TAX)
    repo.add(_plan(date(2026, 11, 9), keys=(SOUND,)))
    repo.add(_plan(date(2026, 11, 10), keys=(SOUND, FLUENCY)))
    repo.add(_plan(date(2026, 11, 11), keys=(SOUND_2,)))
    repo.add(_plan(DAY, keys=(CLARITY,)))

    history = repo.recent_focus_keys(before=DAY, limit=2)

    assert history == {
        TAX.get(SOUND).skill: [SOUND_2, SOUND],
        TAX.get(FLUENCY).skill: [FLUENCY],
    }


def test_recent_prompt_ids_excludes_today_and_later(db_engine: Engine) -> None:
    for item in ("p1", "p2", "p3", "p4"):
        _insert_content(db_engine, item)
    repo = DailyPlanRepository(db_engine, TAX)
    for day, item in (
        (date(2026, 11, 10), "p1"),
        (date(2026, 11, 11), "p2"),
        (DAY, "p3"),
        (date(2026, 11, 13), "p4"),
    ):
        prompt = PromptCandidate(id=item, text="text", target_keys=(SOUND,))
        repo.add(_plan(day, prompt=prompt))

    assert repo.recent_prompt_ids(before=DAY, limit=3) == ["p2", "p1"]


def test_schema_unique_for_date(db_engine: Engine) -> None:
    row: dict[str, Any] = {
        "for_date": DAY.isoformat(),
        "focus_json": "[]",
        "prompt_item_id": None,
        "drills_json": "{}",
        "seed": 1,
    }
    with db_engine.begin() as conn:
        conn.execute(insert(daily_plans).values(id="a", **row))
    with pytest.raises(IntegrityError), db_engine.begin() as conn:
        conn.execute(insert(daily_plans).values(id="b", **row))


def test_prompt_bank_skips_retired_and_non_prompt_items(db_engine: Engine) -> None:
    _insert_content(db_engine, "a")
    _insert_content(db_engine, "b", retired_at=NOW)
    _insert_content(db_engine, "c", kind="passage_sentence")
    _insert_content(db_engine, "d", keys=(SOUND, FLUENCY))

    bank = PromptBankRepository(db_engine).prompts()

    assert [p.id for p in bank] == ["a", "d"]
    assert bank[1].target_keys == (SOUND, FLUENCY)
