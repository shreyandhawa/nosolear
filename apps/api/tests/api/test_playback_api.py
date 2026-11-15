"""Playback: the stored recording, and the model voice (POST synthesizes, GET only serves)."""

from collections.abc import Callable

import pytest
from harness import Harness
from sqlalchemy import select

from nosolear.adapters.tts_cache import CachedSynthesizer
from nosolear.persistence.models import content_items


def test_get_recording_serves_the_stored_wav(harness: Harness) -> None:
    attempt_id = harness.attempt(step="speak", scripted=True, reference_text="very good")
    harness.upload(attempt_id, "very good")
    response = harness.client.get(f"/api/attempts/{attempt_id}/recording")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content[:4] == b"RIFF"
    missing = harness.client.get("/api/attempts/no-such-attempt/recording")
    assert missing.status_code == 404


def _content_id(harness: Harness) -> str:
    with harness.engine.connect() as conn:
        return str(conn.execute(select(content_items.c.id).limit(1)).scalar_one())


def test_post_model_voice_synthesizes_stored_text_and_returns_a_clip(harness: Harness) -> None:
    body = {"source": "content_item", "id": _content_id(harness), "rate_percent": -20}
    response = harness.client.post("/api/model-voice", json=body)
    assert response.status_code == 200, response.text
    clip_id = response.json()["clip_id"]
    served = harness.client.get(f"/api/model-voice/{clip_id}")
    assert served.status_code == 200
    assert served.content[:4] == b"RIFF"
    unknown = {"source": "feedback_item", "id": "no-such-item"}
    assert harness.client.post("/api/model-voice", json=unknown).status_code == 404
    assert (
        harness.client.post("/api/model-voice", json={**body, "rate_percent": 90}).status_code
        == 422
    )


def test_get_model_voice_never_calls_the_synthesizer(
    make_harness: Callable[..., Harness], monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = make_harness()
    body = {"source": "content_item", "id": _content_id(harness)}
    clip_id = harness.client.post("/api/model-voice", json=body).json()["clip_id"]

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a GET reached the synthesizer")

    monkeypatch.setattr(CachedSynthesizer, "synthesize", refuse)
    assert harness.client.get(f"/api/model-voice/{clip_id}").status_code == 200
    assert harness.client.get(f"/api/model-voice/{'0' * 64}").status_code == 404
    assert harness.client.get("/api/model-voice/not-a-hash").status_code == 422
