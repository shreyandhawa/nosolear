"""`/api/plan/today`: today's daily plan, in the configured zone's local date.

`POST` builds the plan once per local day (201) and returns the stored one afterwards (200). `GET`
only reads: it never builds a plan, so it has no side effect and is safe to poll (§15)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from nosolear.api.deps import (
    get_clock,
    get_daily_plan_store,
    get_profile_repository,
    get_prompt_bank,
    get_recheck_store,
    get_scored_keys,
    get_settings,
    load_active_pack,
)
from nosolear.api.errors import ApiError
from nosolear.api.schemas import (
    DrillOut,
    FocusOut,
    PlanOut,
    PlanStepOut,
    ProbeOut,
    PromptOut,
)
from nosolear.app.build_daily_plan import build_daily_plan, plan_date
from nosolear.domain.packs import PackError
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.ports.clock import Clock
from nosolear.ports.plan import (
    DailyPlanStore,
    ProfileReader,
    PromptBank,
    RecheckStore,
    ScoredKeys,
    StoredPlan,
)
from nosolear.settings import Settings

router = APIRouter()


def _plan_out(stored: StoredPlan) -> PlanOut:
    plan = stored.plan
    return PlanOut(
        id=stored.id,
        for_date=plan.for_date,
        seed=plan.seed,
        protocol_version=plan.protocol_version,
        foci=[
            FocusOut(
                skill=f.skill.value,
                error_key=f.error_key,
                description=DEFAULT_TAXONOMY.get(f.error_key).description,
                impact=f.impact,
                status=f.status.value,
                p_hat=f.p_hat,
                provisional=f.provisional,
                source=f.source,
            )
            for f in plan.foci
        ],
        probe=None
        if plan.probe is None
        else ProbeOut(
            skill=plan.probe.skill.value,
            error_key=plan.probe.error_key,
            due_at=plan.probe.due_at,
        ),
        prompt=None
        if plan.prompt is None
        else PromptOut(
            id=plan.prompt.id,
            text=plan.prompt.text,
            target_keys=list(plan.prompt.target_keys),
        ),
        drills=[
            DrillOut(
                skill=d.skill.value,
                error_key=d.error_key,
                drill_family=d.drill_family,
            )
            for d in plan.drills
        ],
        steps=[
            PlanStepOut(
                kind=s.kind.value,
                skill=None if s.skill is None else s.skill.value,
                duration_s=s.duration_s,
            )
            for s in plan.steps
        ],
    )


@router.post(
    "/api/plan/today",
    operation_id="buildTodayPlan",
    status_code=201,
    responses={200: {"description": "today's plan was already built"}},
)
def build_today_plan(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    clock: Annotated[Clock, Depends(get_clock)],
    plans: Annotated[DailyPlanStore, Depends(get_daily_plan_store)],
    profiles: Annotated[ProfileReader, Depends(get_profile_repository)],
    rechecks: Annotated[RecheckStore, Depends(get_recheck_store)],
    prompts: Annotated[PromptBank, Depends(get_prompt_bank)],
    scoring: Annotated[ScoredKeys, Depends(get_scored_keys)],
) -> PlanOut:
    try:
        pack = load_active_pack(settings)
    except PackError:
        raise ApiError(409, "pack_unavailable", "The language pack could not be loaded.") from None
    today = plan_date(clock.now(), settings.tzinfo)
    existed = plans.get(today) is not None
    stored = build_daily_plan(
        plans=plans,
        profiles=profiles,
        rechecks=rechecks,
        prompts=prompts,
        scoring=scoring,
        taxonomy=DEFAULT_TAXONOMY,
        pack=pack,
        clock=clock,
        tz=settings.tzinfo,
    )
    if existed:
        response.status_code = 200
    return _plan_out(stored)


@router.get("/api/plan/today", operation_id="getTodayPlan")
def get_today_plan(
    settings: Annotated[Settings, Depends(get_settings)],
    clock: Annotated[Clock, Depends(get_clock)],
    plans: Annotated[DailyPlanStore, Depends(get_daily_plan_store)],
) -> PlanOut:
    stored = plans.get(plan_date(clock.now(), settings.tzinfo))
    if stored is None:
        raise ApiError(404, "no_plan_for_today", "No plan has been built for today yet.")
    return _plan_out(stored)
