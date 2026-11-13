"""`POST /api/rescore` queues a re-score job."""

from harness import Harness


def test_rescore_endpoint_queues_a_rescore_job(harness: Harness) -> None:
    r = harness.client.post("/api/rescore")
    assert r.status_code == 202
    harness.drain()
    assert harness.client.get(f"/api/jobs/{r.json()['job_id']}").json()["status"] == "done"


def test_openapi_operation_id(harness: Harness) -> None:
    spec = harness.client.app.openapi()  # pyright: ignore[reportAttributeAccessIssue]
    assert spec["paths"]["/api/rescore"]["post"]["operationId"] == "startRescore"
