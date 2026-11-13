import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from factories import FixedClock, loopback_client, make_settings
from fakes import FakeStep
from fastapi import FastAPI

from nosolear.api.app import create_app
from nosolear.api.deps import Services
from nosolear.app.steps import StepRegistry
from nosolear.domain.errors import ProviderUnavailable
from nosolear.domain.jobs import JobKind

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
ANALYZE_STEPS = ("score", "transcribe", "probe", "coach", "extract")
PLANTED = "sk-planted-secret"


def _app(tmp_path: Path, steps: dict[str, FakeStep]) -> FastAPI:
    registry = StepRegistry()
    for step in steps.values():
        registry.register(JobKind.ANALYZE, step)
    return create_app(
        make_settings(data_dir=tmp_path),
        step_registry=registry,
        start_runner=False,
        clock=FixedClock(NOW),
    )


def _services(app: FastAPI) -> Services:
    return cast(Services, app.state.services)


def _working() -> dict[str, FakeStep]:
    return {name: FakeStep(name) for name in ANALYZE_STEPS}


def _enqueue_and_run(app: FastAPI) -> str:
    services = _services(app)
    job = services.jobs.enqueue(JobKind.ANALYZE, None)
    services.runner.run_pending()
    return job.id


def test_get_job_shows_progress_and_steps(tmp_path: Path) -> None:
    app = _app(tmp_path, _working())
    with loopback_client(app) as client:
        job_id = _enqueue_and_run(app)
        r = client.get(f"/api/jobs/{job_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == job_id
    assert body["kind"] == "analyze"
    assert body["attempt_id"] is None
    assert body["status"] == "done"
    assert body["progress"] == 1.0
    assert [s["name"] for s in body["steps"]] == list(ANALYZE_STEPS)
    assert all(s["state"] == "done" for s in body["steps"])
    assert set(body["steps"][0]) == {"name", "state", "error_code", "message"}


def test_get_unknown_job_is_404_with_error_body(tmp_path: Path) -> None:
    with loopback_client(_app(tmp_path, _working())) as client:
        r = client.get("/api/jobs/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"code": "unknown_job", "message": "No job has this id."}


def test_failed_step_shows_its_fixed_safe_message(tmp_path: Path) -> None:
    steps = _working()
    steps["score"] = FakeStep("score", raises=ProviderUnavailable())
    app = _app(tmp_path, steps)
    with loopback_client(app) as client:
        job_id = _enqueue_and_run(app)
        body = client.get(f"/api/jobs/{job_id}").json()
    assert body["status"] == "failed"
    assert body["steps"][0] == {
        "name": "score",
        "state": "failed",
        "error_code": "provider_unavailable",
        "message": "The speech or language provider is unavailable.",
    }


def test_unexpected_error_text_never_reaches_the_api(tmp_path: Path) -> None:
    steps = _working()
    steps["transcribe"] = FakeStep("transcribe", raises=RuntimeError(PLANTED))
    app = _app(tmp_path, steps)
    with loopback_client(app) as client:
        job_id = _enqueue_and_run(app)
        job_text = client.get(f"/api/jobs/{job_id}").text
        openapi_text = client.get("/openapi.json").text
    assert PLANTED not in job_text
    assert PLANTED not in openapi_text
    by_name = {s["name"]: s for s in json.loads(job_text)["steps"]}
    assert by_name["transcribe"]["error_code"] == "internal_error"
    assert by_name["transcribe"]["message"] == "The step failed unexpectedly."
    assert by_name["coach"]["state"] == "blocked"


def test_resume_endpoint_finishes_a_failed_job(tmp_path: Path) -> None:
    steps = _working()
    steps["score"] = FakeStep("score", raises=ProviderUnavailable())
    app = _app(tmp_path, steps)
    with loopback_client(app) as client:
        job_id = _enqueue_and_run(app)
        steps["score"].raises = None  # the provider is back
        resumed = client.post(f"/api/jobs/{job_id}/resume")
        assert resumed.status_code == 200
        assert resumed.json()["status"] == "queued"
        _services(app).runner.run_pending()
        done = client.get(f"/api/jobs/{job_id}").json()
    assert done["status"] == "done"
    assert done["progress"] == 1.0


def test_resuming_a_job_that_is_not_failed_is_409(tmp_path: Path) -> None:
    app = _app(tmp_path, _working())
    with loopback_client(app) as client:
        job_id = _enqueue_and_run(app)
        r = client.post(f"/api/jobs/{job_id}/resume")
    assert r.status_code == 409
    assert r.json() == {"code": "job_not_resumable", "message": "Only a failed job can be resumed."}


def test_resuming_an_unknown_job_is_404(tmp_path: Path) -> None:
    with loopback_client(_app(tmp_path, _working())) as client:
        r = client.post("/api/jobs/nope/resume")
    assert r.status_code == 404
    assert r.json() == {"code": "unknown_job", "message": "No job has this id."}


def test_get_job_is_side_effect_free(tmp_path: Path) -> None:
    steps = _working()
    steps["score"] = FakeStep("score", raises=ProviderUnavailable())
    app = _app(tmp_path, steps)
    with loopback_client(app) as client:
        job_id = _enqueue_and_run(app)
        jobs = _services(app).jobs
        before = jobs.get(job_id)
        for _ in range(3):
            assert client.get(f"/api/jobs/{job_id}").status_code == 200
        assert jobs.get(job_id) == before
