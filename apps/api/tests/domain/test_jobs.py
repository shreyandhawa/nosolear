from nosolear.domain.jobs import (
    JOB_PLANS,
    JobKind,
    JobStatus,
    StepRecord,
    StepState,
    final_status,
    initial_steps,
    progress_of,
    recover_running,
    resume_plan,
)

ANALYZE_NAMES = ["score", "transcribe", "probe", "coach", "extract"]


def _steps(**states: StepState) -> tuple[StepRecord, ...]:
    """The analyze plan with the named steps in the given states, the rest PENDING."""
    return tuple(
        StepRecord(
            name,
            states.get(name, StepState.PENDING),
            error_code="boom"
            if states.get(name) in (StepState.FAILED, StepState.BLOCKED)
            else None,
            message="msg" if states.get(name) in (StepState.FAILED, StepState.BLOCKED) else None,
        )
        for name in ANALYZE_NAMES
    )


def _states(steps: tuple[StepRecord, ...]) -> dict[str, StepState]:
    return {step.name: step.state for step in steps}


def test_plans_match_architecture_order():
    assert [s.name for s in JOB_PLANS[JobKind.ANALYZE]] == ANALYZE_NAMES
    assert [s.name for s in JOB_PLANS[JobKind.RESCORE]] == ["extract"]
    coach = JOB_PLANS[JobKind.ANALYZE][3]
    assert coach.needs == ("transcribe",)
    extract = JOB_PLANS[JobKind.ANALYZE][4]
    assert extract.uses == ("score", "transcribe", "probe", "coach")


def test_initial_steps_all_pending():
    steps = initial_steps(JobKind.ANALYZE)
    assert [s.name for s in steps] == ANALYZE_NAMES
    assert all(s.state is StepState.PENDING for s in steps)
    assert all(s.error_code is None and s.message is None for s in steps)


def test_progress_counts_settled_steps():
    steps = (
        StepRecord("a", StepState.DONE),
        StepRecord("b", StepState.SKIPPED),
        StepRecord("c", StepState.FAILED),
        StepRecord("d", StepState.BLOCKED),
        StepRecord("e", StepState.RUNNING),
        StepRecord("f", StepState.PENDING),
    )
    assert progress_of(steps) == 4 / 6
    assert progress_of(()) == 0.0


def test_final_status():
    assert final_status(_steps()) is JobStatus.DONE
    assert final_status(_steps(score=StepState.DONE, probe=StepState.SKIPPED)) is JobStatus.DONE
    assert final_status(_steps(score=StepState.FAILED)) is JobStatus.FAILED
    assert final_status(_steps(coach=StepState.BLOCKED)) is JobStatus.FAILED


def test_resume_resets_failed_and_dependents():
    steps = _steps(coach=StepState.FAILED, extract=StepState.DONE, score=StepState.DONE)
    resumed = _states(resume_plan(JobKind.ANALYZE, steps))
    assert resumed["coach"] is StepState.PENDING
    assert resumed["extract"] is StepState.PENDING
    assert resumed["score"] is StepState.DONE
    assert resumed["transcribe"] is StepState.PENDING
    assert resumed["probe"] is StepState.PENDING


def test_resume_resets_blocked_chain_and_keeps_independent_steps():
    steps = _steps(
        score=StepState.DONE,
        probe=StepState.DONE,
        transcribe=StepState.FAILED,
        coach=StepState.BLOCKED,
        extract=StepState.DONE,
    )
    resumed = resume_plan(JobKind.ANALYZE, steps)
    assert _states(resumed) == {
        "score": StepState.DONE,
        "transcribe": StepState.PENDING,
        "probe": StepState.DONE,
        "coach": StepState.PENDING,
        "extract": StepState.PENDING,
    }
    assert all(s.error_code is None and s.message is None for s in resumed if s.name != "score")


def test_recover_running_resets_running_step_only():
    steps = (
        StepRecord("score", StepState.DONE),
        StepRecord("transcribe", StepState.RUNNING, error_code="x", message="y"),
        StepRecord("probe", StepState.FAILED, error_code="z", message="w"),
    )
    recovered = recover_running(steps)
    assert recovered[0] == steps[0]
    assert recovered[1] == StepRecord("transcribe", StepState.PENDING)
    assert recovered[2] == steps[2]
