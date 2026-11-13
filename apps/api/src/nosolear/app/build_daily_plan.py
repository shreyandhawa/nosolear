"""Today's plan: built once per local date, then frozen for that day (ARCHITECTURE §6.6, §8.2).

The date is the local date in the configured zone, so a plan rolls over at local midnight. A call
that only crosses UTC midnight stays on the same local date and returns the same plan. Ledger cap
periods stay UTC; only this use case reads the zone.
"""

from datetime import date, datetime, tzinfo

from nosolear.domain.daily_plan import assemble_plan
from nosolear.domain.packs import LanguagePack
from nosolear.domain.selection import DEFAULT_SELECTION, seed_for_date, select
from nosolear.domain.taxonomy import Taxonomy
from nosolear.ports.clock import Clock
from nosolear.ports.plan import (
    DailyPlanStore,
    ProfileReader,
    PromptBank,
    RecheckStore,
    ScoredKeys,
    StoredPlan,
)

RECENT_PROMPTS = 3


def plan_date(now: datetime, tz: tzinfo) -> date:
    """The local date a plan is kept for: the same for every call within one local day."""
    return now.astimezone(tz).date()


def build_daily_plan(
    *,
    plans: DailyPlanStore,
    profiles: ProfileReader,
    rechecks: RecheckStore,
    prompts: PromptBank,
    scoring: ScoredKeys,
    taxonomy: Taxonomy,
    pack: LanguagePack,
    clock: Clock,
    tz: tzinfo,
) -> StoredPlan:
    """The stored plan for today's local date, built and stored first if there is none."""
    now = clock.now()
    day = plan_date(now, tz)
    existing = plans.get(day)
    if existing is not None:
        return existing
    selection = select(
        profile=profiles.latest(),
        taxonomy=taxonomy,
        pack=pack,
        seed=seed_for_date(day),
        now=now,
        history=plans.recent_focus_keys(before=day, limit=DEFAULT_SELECTION.max_streak),
        rechecks=rechecks.load(),
        is_scored=scoring.is_scored,
    )
    plan = assemble_plan(
        for_date=day,
        selection=selection,
        prompts=prompts.prompts(),
        recent_prompt_ids=plans.recent_prompt_ids(before=day, limit=RECENT_PROMPTS),
        taxonomy=taxonomy,
    )
    return plans.add(plan)
