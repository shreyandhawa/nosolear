from fastapi.testclient import TestClient

from nosolear.api.app import create_app
from nosolear.domain.profile import ALGO_VERSION, Profile
from nosolear.domain.taxonomy import TAXONOMY_VERSION


def test_profile_empty_db(client_with_tmp_db: TestClient):
    r = client_with_tmp_db.get("/api/profile")
    assert r.status_code == 200
    assert r.json() == {
        "as_of": None,
        "taxonomy_version": TAXONOMY_VERSION,
        "algo_version": ALGO_VERSION,
        "entries": [],
    }


def test_profile_returns_entries_in_priority_order(
    client_with_tmp_db: TestClient, seeded_profile: Profile
):
    body = client_with_tmp_db.get("/api/profile").json()
    assert [e["error_key"] for e in body["entries"]] == [
        e.definition.key for e in seeded_profile.entries
    ]
    first = body["entries"][0]
    assert first["status"] in {"unknown", "active", "improving", "watching", "mastered"}
    assert set(first) == {
        "error_key",
        "skill",
        "family",
        "description",
        "impact",
        "p_hat",
        "ci_low",
        "ci_high",
        "n_eff",
        "status",
        "priority",
        "last_seen_at",
    }


def test_openapi_operation_id():
    schema = create_app().openapi()
    assert schema["paths"]["/api/profile"]["get"]["operationId"] == "getProfile"
