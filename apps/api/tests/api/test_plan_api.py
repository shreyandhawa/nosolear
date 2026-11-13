"""`/api/plan/today`: POST builds today's plan (201, then 200 the same day). GET only reads."""

from datetime import UTC, datetime
from pathlib import Path

from factories import FixedClock, count, loopback_client, make_settings
from fastapi.testclient import TestClient

from nosolear.api.app import create_app

PLAN = "/api/plan/today"
SKILLS = {"sounds", "on_the_spot", "articulate"}


def _plan_count(client: TestClient) -> int:
    return count(client.app.state.engine, "daily_plans")  # pyright: ignore[reportAttributeAccessIssue]


def test_get_before_post_is_404(client_with_tmp_db: TestClient) -> None:
    response = client_with_tmp_db.get(PLAN)

    assert response.status_code == 404
    assert response.json()["code"] == "no_plan_for_today"
    assert _plan_count(client_with_tmp_db) == 0


def test_post_creates_then_returns_same_plan(client_with_tmp_db: TestClient) -> None:
    first = client_with_tmp_db.post(PLAN)
    second = client_with_tmp_db.post(PLAN)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()
    assert _plan_count(client_with_tmp_db) == 1


def test_get_after_post_matches(client_with_tmp_db: TestClient) -> None:
    posted = client_with_tmp_db.post(PLAN)

    fetched = client_with_tmp_db.get(PLAN)

    assert fetched.status_code == 200
    assert fetched.json() == posted.json()


def test_get_has_no_side_effects(client_with_tmp_db: TestClient) -> None:
    client_with_tmp_db.get(PLAN)
    assert _plan_count(client_with_tmp_db) == 0

    client_with_tmp_db.post(PLAN)
    before = _plan_count(client_with_tmp_db)
    client_with_tmp_db.get(PLAN)

    assert _plan_count(client_with_tmp_db) == before == 1


def test_plan_has_one_focus_per_skill(
    client_with_tmp_db: TestClient, seeded_profile: object
) -> None:
    body = client_with_tmp_db.post(PLAN).json()

    skills = [f["skill"] for f in body["foci"]]
    assert sorted(skills) == sorted(SKILLS)


def test_empty_db_still_returns_a_plan(client_with_tmp_db: TestClient) -> None:
    response = client_with_tmp_db.post(PLAN)

    assert response.status_code == 201
    body = response.json()
    assert len(body["foci"]) == 3
    assert {f["source"] for f in body["foci"]} == {"fallback"}


def test_response_fields_exact(client_with_tmp_db: TestClient, seeded_profile: object) -> None:
    body = client_with_tmp_db.post(PLAN).json()

    assert set(body) == {
        "id",
        "for_date",
        "seed",
        "protocol_version",
        "foci",
        "probe",
        "prompt",
        "drills",
        "steps",
    }
    for focus in body["foci"]:
        assert set(focus) == {
            "skill",
            "error_key",
            "description",
            "impact",
            "status",
            "p_hat",
            "provisional",
            "source",
        }
    for drill in body["drills"]:
        assert set(drill) == {"skill", "error_key", "drill_family"}
    for step in body["steps"]:
        assert set(step) == {"kind", "skill", "duration_s"}
    if body["prompt"] is not None:
        assert set(body["prompt"]) == {"id", "text", "target_keys"}


def test_route_uses_the_configured_zone(tmp_path: Path) -> None:
    clock = FixedClock(datetime(2026, 11, 12, 18, 20, tzinfo=UTC))  # 00:05 on the 13th in Kathmandu
    app = create_app(make_settings(data_dir=tmp_path, timezone="Asia/Kathmandu"), clock=clock)

    with loopback_client(app) as client:
        assert client.post(PLAN).json()["for_date"] == "2026-11-13"
