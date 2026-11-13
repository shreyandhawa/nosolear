"""The daily plan use case: one plan per local date, frozen for the day, with history, prompts,
probes and the unscored-key rule. Fakes come from `fakes.py`; the clock is `FixedClock`."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from factories import NOW, PACK, TAX, FixedClock, entry, profile_of
from fakes import (
    FakeDailyPlanStore,
    FakeProfileReader,
    FakePromptBank,
    FakeRecheckStore,
    FakeScoredKeys,
)

from nosolear.app.build_daily_plan import build_daily_plan
from nosolear.domain.daily_plan import PLAN_PROTOCOL_VERSION, PLAN_STEPS, DailyPlan, PromptCandidate
from nosolear.domain.rechecks import RecheckState
from nosolear.domain.selection import Focus, seed_for_date
from nosolear.domain.status import Status
from nosolear.domain.taxonomy import Skill
from nosolear.ports.plan import StoredPlan

KATHMANDU = ZoneInfo("Asia/Kathmandu")
SOUND = "sound.sub.v.w"
SOUND_2 = "sound.sub.ʃ.s"
FLUENCY = "fluency.filler"
DAY = date(2026, 11, 12)


def _build(
    *,
    plans: FakeDailyPlanStore,
    profiles: FakeProfileReader,
    rechecks: FakeRecheckStore | None = None,
    prompts: FakePromptBank | None = None,
    scoring: FakeScoredKeys | None = None,
    at: datetime,
    tz: ZoneInfo = KATHMANDU,
) -> StoredPlan:
    return build_daily_plan(
        plans=plans,
        profiles=profiles,
        rechecks=rechecks or FakeRecheckStore(),
        prompts=prompts or FakePromptBank(),
        scoring=scoring or FakeScoredKeys(),
        taxonomy=TAX,
        pack=PACK,
        clock=FixedClock(at),
        tz=tz,
    )


def _profile_with_sounds(*keys: str) -> FakeProfileReader:
    entries = [entry(key, a=3, b=7, status=Status.ACTIVE) for key in keys]
    return FakeProfileReader(profile_of(entries))


def _stored_focus(day: date, key: str) -> StoredPlan:
    definition = TAX.get(key)
    focus = Focus(
        skill=definition.skill,
        error_key=key,
        impact=definition.impact,
        status=Status.ACTIVE,
        p_hat=0.3,
        sampled_rate=0.3,
        score=1.0,
        runner_up_score=None,
        provisional=False,
        source="profile",
    )
    plan = DailyPlan(
        for_date=day,
        seed=seed_for_date(day),
        foci=(focus,),
        probe=None,
        prompt=None,
        drills=(),
        steps=PLAN_STEPS,
        protocol_version=PLAN_PROTOCOL_VERSION,
    )
    return StoredPlan(id=f"plan-{day.isoformat()}", plan=plan)


def test_same_local_day_returns_frozen_plan() -> None:
    plans = FakeDailyPlanStore()
    profiles = _profile_with_sounds(SOUND, SOUND_2)
    first = _build(plans=plans, profiles=profiles, at=datetime(2026, 11, 12, 10, 0, tzinfo=UTC))

    # Misses arrive later the same local day: the plan must not change.
    profiles.profile = profile_of([entry(FLUENCY, a=9, b=1, status=Status.ACTIVE)])
    later = _build(plans=plans, profiles=profiles, at=datetime(2026, 11, 12, 12, 0, tzinfo=UTC))

    assert later == first
    assert later.plan.for_date == DAY


def test_next_local_day_builds_new_plan() -> None:
    plans = FakeDailyPlanStore()
    profiles = _profile_with_sounds(SOUND)
    before_midnight = _build(
        plans=plans, profiles=profiles, at=datetime(2026, 11, 12, 18, 10, tzinfo=UTC)
    )
    after_midnight = _build(
        plans=plans, profiles=profiles, at=datetime(2026, 11, 12, 18, 20, tzinfo=UTC)
    )

    assert before_midnight.plan.for_date == date(2026, 11, 12)  # 23:55 local
    assert after_midnight.plan.for_date == date(2026, 11, 13)  # 00:05 local
    assert after_midnight.id != before_midnight.id


def test_utc_midnight_alone_does_not_roll_over() -> None:
    plans = FakeDailyPlanStore()
    profiles = _profile_with_sounds(SOUND)
    early = _build(plans=plans, profiles=profiles, at=datetime(2026, 11, 12, 23, 50, tzinfo=UTC))
    late = _build(plans=plans, profiles=profiles, at=datetime(2026, 11, 13, 0, 10, tzinfo=UTC))

    assert early.plan.for_date == date(2026, 11, 13)  # 05:35 local
    assert late == early


def test_streak_history_feeds_selection() -> None:
    at = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
    profiles = _profile_with_sounds(SOUND, SOUND_2)
    no_history = _build(plans=FakeDailyPlanStore(), profiles=profiles, at=at)

    plans = FakeDailyPlanStore()
    for day in (date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 11)):
        plans.plans[day] = _stored_focus(day, SOUND)
    with_history = _build(plans=plans, profiles=profiles, at=at)

    sounds_without = next(f for f in no_history.plan.foci if f.skill is Skill.SOUNDS)
    sounds_with = next(f for f in with_history.plan.foci if f.skill is Skill.SOUNDS)
    assert sounds_without.error_key == SOUND
    assert sounds_with.error_key == SOUND_2


def test_recent_prompts_are_not_repeated() -> None:
    plans = FakeDailyPlanStore()
    yesterday = date(2026, 11, 11)
    used = PromptCandidate(id="p-used", text="Used yesterday.", target_keys=(SOUND,))
    fresh = PromptCandidate(id="p-fresh", text="Not yet used.", target_keys=())
    plans.plans[yesterday] = StoredPlan(
        id="old",
        plan=DailyPlan(
            for_date=yesterday,
            seed=seed_for_date(yesterday),
            foci=(),
            probe=None,
            prompt=used,
            drills=(),
            steps=PLAN_STEPS,
            protocol_version=PLAN_PROTOCOL_VERSION,
        ),
    )
    built = _build(
        plans=plans,
        profiles=_profile_with_sounds(SOUND),
        prompts=FakePromptBank([used, fresh]),
        at=datetime(2026, 11, 12, 8, 0, tzinfo=UTC),
    )

    assert built.plan.prompt == fresh


def test_empty_prompt_bank_gives_no_prompt() -> None:
    built = _build(
        plans=FakeDailyPlanStore(),
        profiles=_profile_with_sounds(SOUND),
        at=datetime(2026, 11, 12, 8, 0, tzinfo=UTC),
    )

    assert built.plan.prompt is None


def test_no_profile_builds_fallback_plan() -> None:
    built = _build(
        plans=FakeDailyPlanStore(),
        profiles=FakeProfileReader(None),
        at=datetime(2026, 11, 12, 8, 0, tzinfo=UTC),
    )

    assert {f.skill for f in built.plan.foci} == set(Skill)
    assert len(built.plan.foci) == len(Skill)
    assert all(f.source == "fallback" for f in built.plan.foci)
    assert built.plan.prompt is None
    assert built.plan.probe is None


def test_unscored_keys_are_not_selected() -> None:
    built = _build(
        plans=FakeDailyPlanStore(),
        profiles=_profile_with_sounds(SOUND, SOUND_2),
        scoring=FakeScoredKeys(unscored={SOUND, SOUND_2}),
        at=datetime(2026, 11, 12, 8, 0, tzinfo=UTC),
    )

    keys = {f.error_key for f in built.plan.foci}
    assert SOUND not in keys
    assert SOUND_2 not in keys


def test_probe_comes_from_due_rechecks() -> None:
    now = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
    profiles = FakeProfileReader(
        profile_of([entry(SOUND_2, a=1, b=30, status=Status.MASTERED)], as_of=NOW)
    )
    rechecks = FakeRecheckStore({SOUND_2: RecheckState(stage=0, next_at=NOW)})

    built = _build(plans=FakeDailyPlanStore(), profiles=profiles, rechecks=rechecks, at=now)

    assert built.plan.probe is not None
    assert built.plan.probe.error_key == SOUND_2
