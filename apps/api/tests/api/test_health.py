from fastapi.testclient import TestClient

from nosolear.api.app import create_app


def test_health_ok():
    r = TestClient(create_app()).get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
