"""Starting today's daily session: one unscripted `speak` attempt that carries the plan's prompt,
and a repeat start returns the same session and attempt."""

from datetime import UTC, datetime

from factories import FixedClock
from fakes import FakeDailySessionStore

from nosolear.app.start_daily_session import start_daily_session
from nosolear.domain.daily_plan import PLAN_PROTOCOL_VERSION, PLAN_STEPS, DailyPlan, PromptCandidate
from nosolear.domain.selection import seed_for_date
from nosolear.ports.plan import StartedSession, StoredPlan

NOW = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
DAY = NOW.date()


def _stored(prompt: PromptCandidate | None) -> StoredPlan:
    plan = DailyPlan(
        for_date=DAY,
        seed=seed_for_date(DAY),
        foci=(),
        probe=None,
        prompt=prompt,
        drills=(),
        steps=PLAN_STEPS,
        protocol_version=PLAN_PROTOCOL_VERSION,
    )
    return StoredPlan(id="plan-1", plan=plan)


def _start(store: FakeDailySessionStore, stored: StoredPlan) -> StartedSession:
    return start_daily_session(build_plan=lambda: stored, sessions=store, clock=FixedClock(NOW))


def test_creates_one_speak_attempt_with_prompt_item() -> None:
    store = FakeDailySessionStore()
    prompt = PromptCandidate(id="p-1", text="Tell me about your day.", target_keys=())

    started = _start(store, _stored(prompt))

    assert started.created is True
    assert started.plan_id == "plan-1"
    assert len(started.attempts) == 1
    attempt = started.attempts[0]
    assert attempt.step == "speak"
    assert attempt.reference_text is None
    assert attempt.content_item_id == "p-1"


def test_repeat_returns_same_session_and_attempt() -> None:
    store = FakeDailySessionStore()
    stored = _stored(PromptCandidate(id="p-1", text="Tell me.", target_keys=()))

    first = _start(store, stored)
    second = _start(store, stored)

    assert len(store.created) == 1
    assert second.session_id == first.session_id
    assert second.attempts == first.attempts
    assert second.created is False


def test_plan_without_prompt_gives_null_content_item() -> None:
    started = _start(FakeDailySessionStore(), _stored(None))

    assert started.attempts[0].content_item_id is None
