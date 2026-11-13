from hypothesis import given
from hypothesis import strategies as st

from nosolear.domain.jobs import (
    JOB_PLANS,
    JobKind,
    StepRecord,
    StepSpec,
    StepState,
    recover_running,
    resume_plan,
)

KINDS = st.sampled_from(list(JobKind))
STATES = st.sampled_from(list(StepState))


def _record(spec: StepSpec, state: StepState) -> StepRecord:
    failed = state in (StepState.FAILED, StepState.BLOCKED)
    return StepRecord(
        spec.name, state, error_code="code" if failed else None, message="m" if failed else None
    )


@st.composite
def plan_states(draw: st.DrawFn) -> tuple[JobKind, tuple[StepRecord, ...]]:
    kind = draw(KINDS)
    records = tuple(_record(spec, draw(STATES)) for spec in JOB_PLANS[kind])
    return kind, records


def _closure(kind: JobKind, steps: tuple[StepRecord, ...]) -> set[str]:
    """Independent model: the failed or blocked steps, plus every step that needs or uses one."""
    names = {s.name for s in steps if s.state in (StepState.FAILED, StepState.BLOCKED)}
    changed = True
    while changed:
        changed = False
        for spec in JOB_PLANS[kind]:
            if spec.name not in names and set(spec.needs + spec.uses) & names:
                names.add(spec.name)
                changed = True
    return names


@given(plan_states())
def test_resume_never_changes_settled_steps_outside_the_closure(
    case: tuple[JobKind, tuple[StepRecord, ...]],
) -> None:
    kind, steps = case
    closure = _closure(kind, steps)
    resumed = resume_plan(kind, steps)
    for before, after in zip(steps, resumed, strict=True):
        if before.name not in closure and before.state in (StepState.DONE, StepState.SKIPPED):
            assert after == before


@given(plan_states())
def test_after_resume_no_step_is_failed_or_blocked(
    case: tuple[JobKind, tuple[StepRecord, ...]],
) -> None:
    kind, steps = case
    resumed = resume_plan(kind, steps)
    assert not any(s.state in (StepState.FAILED, StepState.BLOCKED) for s in resumed)


@given(plan_states())
def test_resume_is_idempotent(case: tuple[JobKind, tuple[StepRecord, ...]]) -> None:
    kind, steps = case
    once = resume_plan(kind, steps)
    assert resume_plan(kind, once) == once


@given(plan_states())
def test_recover_running_leaves_no_running_step_and_touches_nothing_else(
    case: tuple[JobKind, tuple[StepRecord, ...]],
) -> None:
    _, steps = case
    recovered = recover_running(steps)
    assert not any(s.state is StepState.RUNNING for s in recovered)
    for before, after in zip(steps, recovered, strict=True):
        if before.state is not StepState.RUNNING:
            assert after == before
        else:
            assert after == StepRecord(before.name, StepState.PENDING)
