import json
import typing
from pathlib import Path

from factories import FakeEnvironment
from fastapi.testclient import TestClient

from nosolear.api.app import create_app
from nosolear.api.deps import get_environment, get_readiness_report
from nosolear.api.schemas import ReadinessRowOut
from nosolear.domain.readiness import (
    Component,
    ReadinessReport,
    ReadinessRow,
    ReadinessStatus,
)
from nosolear.settings import Settings

KEY_A = "AzurePlantedKey-0123456789abcdef"
KEY_B = "AnthropicPlantedKey-0123456789abcdef"


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    return {
        str(p.relative_to(root)): (p.stat().st_mtime_ns, p.stat().st_size)
        for p in sorted(root.rglob("*"))
    }


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        azure_speech_key=KEY_A,  # pyright: ignore[reportArgumentType]
        azure_speech_region="westus2",
        anthropic_api_key=KEY_B,  # pyright: ignore[reportArgumentType]
    )


def test_readiness_returns_eight_rows_and_no_key(tmp_path: Path):
    with TestClient(create_app(_settings(tmp_path))) as client:
        r = client.get("/api/readiness")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["ready"], bool)
        assert [row["component"] for row in body["rows"]] == [c.value for c in Component]
        assert all(
            set(row) == {"component", "label", "status", "reason", "fix"} for row in body["rows"]
        )
        azure = body["rows"][0]
        assert azure["label"] == "Azure Speech" and azure["status"] == "ready"
        assert KEY_A not in r.text and KEY_B not in r.text
        assert KEY_A not in json.dumps(client.get("/openapi.json").json())


def test_openapi_lists_the_route_without_keys(tmp_path: Path):
    with TestClient(create_app(_settings(tmp_path))) as client:
        text = client.get("/openapi.json").text
    assert "/api/readiness" in text and "getReadiness" in text
    assert KEY_A not in text and KEY_B not in text


def test_readiness_writes_nothing_under_the_data_dir(tmp_path: Path):
    with TestClient(create_app(_settings(tmp_path))) as client:
        before = _snapshot(tmp_path)
        assert client.get("/api/readiness").status_code == 200
        assert _snapshot(tmp_path) == before


def test_literals_match_the_enums():
    hints = typing.get_type_hints(ReadinessRowOut)
    assert set(typing.get_args(hints["component"])) == {c.value for c in Component}
    assert set(typing.get_args(hints["status"])) == {s.value for s in ReadinessStatus}


def test_route_maps_a_hand_built_report(tmp_path: Path):
    rows = tuple(ReadinessRow(c, ReadinessStatus.READY, "fine", None) for c in Component)
    rows = (
        ReadinessRow(Component.AZURE_SPEECH, ReadinessStatus.MISSING, "no key", "set it"),
        *rows[1:],
    )
    app = create_app(_settings(tmp_path))
    app.dependency_overrides[get_readiness_report] = lambda: ReadinessReport(rows)
    with TestClient(app) as client:
        body = client.get("/api/readiness").json()
    assert body["ready"] is False
    assert [r["label"] for r in body["rows"]] == [
        "Azure Speech",
        "Azure capabilities",
        "Anthropic",
        "Transcriber",
        "Phone probe",
        "Language pack",
        "Data dir",
        "Usage",
    ]
    assert body["rows"][0]["fix"] == "set it"
    assert body["rows"][1]["fix"] is None


def test_environment_dependency_can_be_overridden(tmp_path: Path):
    app = create_app(_settings(tmp_path))
    env = FakeEnvironment(modules={"torch", "transformers"}, executables={"espeak-ng"})
    app.dependency_overrides[get_environment] = lambda: env
    with TestClient(app) as client:
        rows = {r["component"]: r for r in client.get("/api/readiness").json()["rows"]}
    assert rows["phone_probe"]["status"] == "ready"
