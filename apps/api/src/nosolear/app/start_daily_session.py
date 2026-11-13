"""Start today's daily session: the one attempt the daily recording travels on (§8.2).

The session is keyed by the plan, so starting it again returns the session that exists. Its
attempt is an unscripted `speak` whose content item is the plan's prompt, which is the same shape
the baseline recordings use, so the upload and extraction path needs no daily-only branch.
"""

from collections.abc import Callable

from nosolear.ports.clock import Clock
from nosolear.ports.plan import DailySessionStore, StartedSession, StoredPlan


def start_daily_session(
    *,
    build_plan: Callable[[], StoredPlan],
    sessions: DailySessionStore,
    clock: Clock,
) -> StartedSession:
    stored = build_plan()
    existing = sessions.for_plan(stored.id)
    if existing is not None:
        return existing
    prompt = stored.plan.prompt
    return sessions.create(
        plan_id=stored.id,
        prompt_item_id=None if prompt is None else prompt.id,
        started_at=clock.now(),
    )
