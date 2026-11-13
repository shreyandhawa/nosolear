"""SQLAlchemy adapters for the daily plan: the stored plans, the prompt bank and the scored-key
check. The plan's JSON columns are written and read with explicit (de)serializers, never pickle."""

import json
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any, Literal, cast
from uuid import uuid4

from sqlalchemy import Engine, Row, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from nosolear.domain.content import ContentKind
from nosolear.domain.daily_plan import (
    PLAN_STEPS,
    DailyPlan,
    DrillSpec,
    PromptCandidate,
)
from nosolear.domain.selection import Focus, RecheckProbe
from nosolear.domain.status import Status
from nosolear.domain.taxonomy import Skill, Taxonomy
from nosolear.persistence.models import content_items, daily_plans
from nosolear.ports.plan import StoredPlan
from nosolear.ports.scoring_stores import ScoringConfigReader

_UNSIGNED_64 = 2**64
_SIGN_BIT = 2**63


def _seed_column(seed: int) -> int:
    """SQLite integers are signed 64-bit, so a seed in the upper half is stored as its two's
    complement. `_seed_value` reverses it."""
    return seed - _UNSIGNED_64 if seed >= _SIGN_BIT else seed


def _seed_value(stored: int) -> int:
    return stored % _UNSIGNED_64


def _focus_json(focus: Focus) -> dict[str, object]:
    return {
        "skill": focus.skill.value,
        "error_key": focus.error_key,
        "impact": focus.impact,
        "status": focus.status.value,
        "p_hat": focus.p_hat,
        "sampled_rate": focus.sampled_rate,
        "score": focus.score,
        "runner_up_score": focus.runner_up_score,
        "provisional": focus.provisional,
        "source": focus.source,
    }


def _source(value: object) -> Literal["profile", "fallback"]:
    if value == "profile":
        return "profile"
    if value == "fallback":
        return "fallback"
    raise ValueError(f"unknown focus source {value!r}")


def _focus(raw: dict[str, Any]) -> Focus:
    runner_up = raw["runner_up_score"]
    return Focus(
        skill=Skill(raw["skill"]),
        error_key=str(raw["error_key"]),
        impact=int(raw["impact"]),
        status=Status(raw["status"]),
        p_hat=float(raw["p_hat"]),
        sampled_rate=float(raw["sampled_rate"]),
        score=float(raw["score"]),
        runner_up_score=None if runner_up is None else float(runner_up),
        provisional=bool(raw["provisional"]),
        source=_source(raw["source"]),
    )


def _body_json(plan: DailyPlan) -> str:
    """The probe, drills, prompt (with its text) and protocol version. Steps are the protocol's
    constant, so they are not stored."""
    probe = plan.probe
    prompt = plan.prompt
    body: dict[str, object] = {
        "probe": None
        if probe is None
        else {
            "skill": probe.skill.value,
            "error_key": probe.error_key,
            "due_at": probe.due_at.isoformat(),
        },
        "drills": [
            {"skill": d.skill.value, "error_key": d.error_key, "drill_family": d.drill_family}
            for d in plan.drills
        ],
        "prompt": None
        if prompt is None
        else {"id": prompt.id, "text": prompt.text, "target_keys": list(prompt.target_keys)},
        "protocol_version": plan.protocol_version,
    }
    return json.dumps(body, sort_keys=True)


def _stored(row: Row[Any]) -> StoredPlan:
    body = cast(dict[str, Any], json.loads(row.drills_json))
    probe_raw = cast(dict[str, Any] | None, body["probe"])
    prompt_raw = cast(dict[str, Any] | None, body["prompt"])
    probe = (
        None
        if probe_raw is None
        else RecheckProbe(
            skill=Skill(probe_raw["skill"]),
            error_key=str(probe_raw["error_key"]),
            due_at=datetime.fromisoformat(probe_raw["due_at"]),
        )
    )
    prompt = (
        None
        if prompt_raw is None
        else PromptCandidate(
            id=str(prompt_raw["id"]),
            text=str(prompt_raw["text"]),
            target_keys=tuple(cast(list[str], prompt_raw["target_keys"])),
        )
    )
    foci = cast(list[dict[str, Any]], json.loads(row.focus_json))
    drills = cast(list[dict[str, Any]], body["drills"])
    plan = DailyPlan(
        for_date=date.fromisoformat(row.for_date),
        seed=_seed_value(row.seed),
        foci=tuple(_focus(f) for f in foci),
        probe=probe,
        prompt=prompt,
        drills=tuple(
            DrillSpec(
                skill=Skill(d["skill"]),
                error_key=str(d["error_key"]),
                drill_family=str(d["drill_family"]),
            )
            for d in drills
        ),
        steps=PLAN_STEPS,
        protocol_version=int(body["protocol_version"]),
    )
    return StoredPlan(id=row.id, plan=plan)


class DailyPlanRepository:
    """`DailyPlanStore`: one row per local date, the first one stored wins."""

    def __init__(self, engine: Engine, taxonomy: Taxonomy) -> None:
        self._engine = engine
        self._taxonomy = taxonomy

    def get(self, for_date: date) -> StoredPlan | None:
        stmt = select(daily_plans).where(daily_plans.c.for_date == for_date.isoformat())
        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()
        return None if row is None else _stored(row)

    def add(self, plan: DailyPlan) -> StoredPlan:
        values = {
            "id": uuid4().hex,
            "for_date": plan.for_date.isoformat(),
            "focus_json": json.dumps([_focus_json(f) for f in plan.foci], sort_keys=True),
            "prompt_item_id": None if plan.prompt is None else plan.prompt.id,
            "drills_json": _body_json(plan),
            "seed": _seed_column(plan.seed),
        }
        stmt = sqlite_insert(daily_plans).values(**values)
        with self._engine.begin() as conn:
            conn.execute(stmt.on_conflict_do_nothing(index_elements=["for_date"]))
        stored = self.get(plan.for_date)
        if stored is None:
            raise RuntimeError("the daily plan was not stored")
        return stored

    def _recent(self, before: date, limit: int) -> Sequence[Any]:
        stmt = (
            select(daily_plans.c.id, daily_plans.c.focus_json, daily_plans.c.prompt_item_id)
            .where(daily_plans.c.for_date < before.isoformat())
            .order_by(daily_plans.c.for_date.desc())
            .limit(limit)
        )
        with self._engine.connect() as conn:
            return conn.execute(stmt).all()

    def recent_focus_keys(self, before: date, limit: int = 3) -> dict[Skill, list[str]]:
        keys: dict[Skill, list[str]] = {}
        for row in self._recent(before, limit):
            for raw in cast(list[dict[str, Any]], json.loads(row.focus_json)):
                keys.setdefault(Skill(raw["skill"]), []).append(str(raw["error_key"]))
        return keys

    def recent_prompt_ids(self, before: date, limit: int = 3) -> list[str]:
        return [row.prompt_item_id for row in self._recent(before, limit) if row.prompt_item_id]


class PromptBankRepository:
    """`PromptBank`: the live prompts, in id order."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def prompts(self) -> list[PromptCandidate]:
        stmt = (
            select(content_items)
            .where(
                content_items.c.kind == ContentKind.PROMPT.value,
                content_items.c.retired_at.is_(None),
            )
            .order_by(content_items.c.id)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [
            PromptCandidate(
                id=row.id,
                text=row.text,
                target_keys=tuple(cast(list[str], json.loads(row.target_keys))),
            )
            for row in rows
        ]


class ScoringCoverage:
    """`ScoredKeys`: a key is scored when the newest config has a live rule for one of its
    detectors. A key the taxonomy does not know is not scored."""

    def __init__(self, configs: ScoringConfigReader, taxonomy: Taxonomy) -> None:
        self._configs = configs
        self._taxonomy = taxonomy

    def is_scored(self, error_key: str) -> bool:
        if error_key not in self._taxonomy:
            return False
        definition = self._taxonomy.get(error_key)
        config = self._configs.newest()
        return any(config.rule_for(d, definition) is not None for d in definition.detectors)
