"""`POST /api/plan/today/session`: the daily session and its one unscripted speak attempt. The
rows are read back from the database, so the schema itself is what is checked."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from harness import Harness
from sqlalchemy import Engine, insert, select
from sqlalchemy.exc import IntegrityError

from nosolear.persistence.models import attempts, sessions

PLAN = "/api/plan/today"
SESSION = "/api/plan/today/session"


def _engine(client: TestClient) -> Engine:
    return client.app.state.engine  # pyright: ignore[reportAttributeAccessIssue]


def test_first_post_201_then_200_same_ids(client_with_tmp_db: TestClient) -> None:
    first = client_with_tmp_db.post(SESSION)
    second = client_with_tmp_db.post(SESSION)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()


def test_creates_plan_if_missing(client_with_tmp_db: TestClient) -> None:
    body = client_with_tmp_db.post(SESSION).json()

    assert client_with_tmp_db.get(PLAN).json()["id"] == body["plan_id"]


def test_attempt_row_is_unscripted_speak_with_content_item(
    client_with_tmp_db: TestClient,
) -> None:
    body = client_with_tmp_db.post(SESSION).json()
    plan = client_with_tmp_db.get(PLAN).json()
    prompt = plan["prompt"]

    with _engine(client_with_tmp_db).connect() as conn:
        rows = conn.execute(
            select(attempts).where(attempts.c.session_id == body["session_id"])
        ).all()

    assert len(rows) == 1
    row = rows[0]
    assert row.step == "speak"
    assert row.scripted is False
    assert row.reference_text is None
    assert row.content_item_id == (None if prompt is None else prompt["id"])
    assert body["attempts"][0]["id"] == row.id
    assert body["attempts"][0]["prompt_text"] == (None if prompt is None else prompt["text"])


def test_session_row_kind_daily_with_plan_id(client_with_tmp_db: TestClient) -> None:
    body = client_with_tmp_db.post(SESSION).json()

    with _engine(client_with_tmp_db).connect() as conn:
        row = conn.execute(select(sessions).where(sessions.c.id == body["session_id"])).one()

    assert row.kind == "daily"
    assert row.plan_id == body["plan_id"]
    assert row.protocol_version == 1


def test_unique_plan_id_index_rejects_second_session(client_with_tmp_db: TestClient) -> None:
    body = client_with_tmp_db.post(SESSION).json()

    with pytest.raises(IntegrityError), _engine(client_with_tmp_db).begin() as conn:
        conn.execute(
            insert(sessions).values(
                id="second",
                kind="daily",
                protocol_version=1,
                started_at=datetime.now(UTC),
                completed_at=None,
                plan_id=body["plan_id"],
            )
        )


def test_daily_attempt_takes_a_recording_like_a_baseline_attempt(
    make_harness: Callable[..., Harness],
) -> None:
    h = make_harness()
    attempt = h.client.post(SESSION).json()["attempts"][0]

    job_id = h.upload(attempt["id"], attempt["prompt_text"] or "Tell me about your day.")

    assert h.drain() >= 1
    assert h.client.get(f"/api/jobs/{job_id}").json()["status"] == "done"
