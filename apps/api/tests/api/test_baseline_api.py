"""`/api/baseline`: start, read, complete and the report, with safe 409 and 404 bodies."""

from collections.abc import Callable

from baseline_fixtures import small_baseline_content
from harness import Harness

from nosolear.domain.coach import Rubric

RUBRIC = Rubric(structure=3, clarity=3, concision=3)


def _started(h: Harness) -> dict[str, object]:
    response = h.client.post("/api/baseline")
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_baseline_endpoints_follow_the_session(make_harness: Callable[..., Harness]):
    h = make_harness(content=small_baseline_content(), rubric=RUBRIC)
    assert h.client.get("/api/baseline").status_code == 404
    assert h.client.get("/api/baseline/report").status_code == 404

    body = _started(h)
    assert body["protocol_version"] == 1 and body["completed_at"] is None
    items = body["items"]
    assert isinstance(items, list) and len(items) == 6
    assert h.client.get("/api/baseline").json()["session_id"] == body["session_id"]

    pending = h.client.post("/api/baseline/complete")
    assert pending.status_code == 409
    assert pending.json() == {
        "code": "baseline_pending",
        "message": (
            "Record every baseline item and wait for its analysis to finish before completing."
        ),
    }
    assert h.client.get("/api/baseline/report").status_code == 404

    for item in items:
        h.upload(item["attempt_id"], item["stand_in_text"])
    h.drain()
    completed = h.client.post("/api/baseline/complete")
    assert completed.status_code == 200, completed.text
    report = completed.json()
    assert report["session_id"] == body["session_id"]
    assert set(report) == {
        "session_id",
        "completed_at",
        "calibration",
        "scoring_config_id",
        "snapshot_id",
        "items",
        "skill_scores",
        "notes",
    }
    fetched = h.client.get("/api/baseline/report")
    assert fetched.status_code == 200 and fetched.json()["snapshot_id"] == report["snapshot_id"]


def test_complete_without_a_session_is_a_safe_409(make_harness: Callable[..., Harness]):
    h = make_harness(content=small_baseline_content())
    response = h.client.post("/api/baseline/complete")
    assert response.status_code == 409
    assert response.json() == {
        "code": "baseline_not_open",
        "message": "No baseline is in progress.",
    }


def test_openapi_operation_ids(make_harness: Callable[..., Harness]):
    h = make_harness(content=small_baseline_content())
    paths = h.client.app.openapi()["paths"]  # pyright: ignore[reportAttributeAccessIssue]
    assert paths["/api/baseline"]["post"]["operationId"] == "startBaseline"
    assert paths["/api/baseline"]["get"]["operationId"] == "getBaseline"
    assert paths["/api/baseline/complete"]["post"]["operationId"] == "completeBaseline"
    assert paths["/api/baseline/report"]["get"]["operationId"] == "getBaselineReport"
