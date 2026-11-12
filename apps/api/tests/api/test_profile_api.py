from pathlib import Path

import pytest
from factories import NEPALI, NOW, SAMPLE_OBS, TAX, FixedClock
from fastapi.testclient import TestClient

from nosolear.api.app import create_app
from nosolear.app.rebuild_profile import rebuild_profile
from nosolear.domain.profile import ALGO_VERSION, Profile
from nosolear.domain.taxonomy import TAXONOMY_VERSION
from nosolear.persistence.repositories import ObservationRepository, ProfileRepository
from nosolear.settings import Settings


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


def test_startup_rebuilds_a_profile_built_under_another_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("NOSOLEAR_PACK", "nepali")
    with TestClient(create_app(Settings(data_dir=tmp_path))) as first:
        engine = first.app.state.engine  # pyright: ignore[reportAttributeAccessIssue]
        ObservationRepository(engine).add_many(SAMPLE_OBS)
        rebuild_profile(
            observations=ObservationRepository(engine),
            profiles=ProfileRepository(engine, TAX),
            taxonomy=TAX,
            pack=NEPALI,
            clock=FixedClock(NOW),
        )
    monkeypatch.setenv("NOSOLEAR_PACK", "neutral")
    with TestClient(create_app(Settings(data_dir=tmp_path))) as second:
        engine = second.app.state.engine  # pyright: ignore[reportAttributeAccessIssue]
        assert ProfileRepository(engine, TAX).latest_pack_id() == "neutral"


def test_invalid_pack_does_not_stop_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.setenv("NOSOLEAR_PACK", "nosuchpack")
    with caplog.at_level("WARNING"), TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        assert client.get("/api/health").status_code == 200
    assert any("nosuchpack" in r.getMessage() for r in caplog.records)
