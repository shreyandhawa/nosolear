"""The calibration routes: their bodies, statuses and safe 409 messages."""

from calibration_fixtures import small_content
from harness import Harness
from security.planted import PLANTED_AZURE_KEY
from sqlalchemy import delete

from nosolear.persistence.models import provider_capabilities


def test_calibration_flow_over_http(make_harness):
    h: Harness = make_harness(content=small_content())
    started = h.client.post("/api/calibration")
    assert started.status_code == 200 and started.json()["status"] == "running"
    run_id = started.json()["run_id"]
    assert h.client.get("/api/calibration").json()["run_id"] == run_id
    refused = h.client.post("/api/calibration/finish")
    assert refused.status_code == 409
    assert refused.json()["message"] == "Record at least one calibration word before finishing."
    first = started.json()["items"][0]
    h.upload(first["attempt_id"], first["stand_in_text"])
    h.drain()
    assert h.client.post("/api/calibration/finish").status_code == 202


def test_get_without_a_run_is_404(make_harness):
    h = make_harness(content=small_content())
    assert h.client.get("/api/calibration").status_code == 404


def test_skip_returns_the_skipped_run(make_harness):
    h = make_harness(content=small_content())
    skipped = h.client.post("/api/calibration/skip")
    assert skipped.status_code == 200 and skipped.json()["status"] == "skipped"


def test_nothing_to_calibrate_is_409_with_a_safe_message(make_harness):
    h: Harness = make_harness(content=small_content())
    with h.engine.begin() as conn:
        conn.execute(delete(provider_capabilities))
    r = h.client.post("/api/calibration")
    assert r.status_code == 409
    assert r.json() == {
        "code": "nothing_to_calibrate",
        "message": "No detector can be calibrated on this install: run nosolear doctor --probe, "
        "or skip calibration.",
    }


def test_responses_never_contain_a_key(make_harness):
    h = make_harness(content=small_content())
    bodies = [
        h.client.post("/api/calibration").text,
        h.client.get("/api/calibration").text,
        h.client.post("/api/calibration/finish").text,
    ]
    assert all(PLANTED_AZURE_KEY not in body for body in bodies)


def test_openapi_operation_ids(harness: Harness):
    spec = harness.client.app.openapi()  # pyright: ignore[reportAttributeAccessIssue]
    ids = {
        spec["paths"]["/api/calibration"]["post"]["operationId"],
        spec["paths"]["/api/calibration"]["get"]["operationId"],
        spec["paths"]["/api/calibration/skip"]["post"]["operationId"],
        spec["paths"]["/api/calibration/finish"]["post"]["operationId"],
    }
    assert ids == {"startCalibration", "getCalibration", "skipCalibration", "finishCalibration"}
