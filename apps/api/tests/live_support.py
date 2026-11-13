from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from nosolear.ports.providers import Synthesizer
from nosolear.settings import Settings

Provider = Literal["azure", "anthropic"]


def _missing(settings: Settings, provider: Provider) -> list[str]:
    if provider == "azure":
        pairs = {
            "NOSOLEAR_AZURE_SPEECH_KEY": settings.azure_speech_key,
            "NOSOLEAR_AZURE_SPEECH_REGION": settings.azure_speech_region,
        }
    else:
        pairs = {"NOSOLEAR_ANTHROPIC_API_KEY": settings.anthropic_api_key}
    return [name for name, value in pairs.items() if value is None]


def require_keys(settings: Settings, *providers: Provider) -> None:
    """Skip the test when a provider's settings are unset. Names variables, never values."""
    missing = [name for provider in providers for name in _missing(settings, provider)]
    if missing:
        pytest.skip("live test needs " + ", ".join(missing) + " (set in env or .env)")


@dataclass
class LiveHarness:
    """The app over the real adapters: the same surface as the oracle harness, without oracles."""

    client: TestClient
    synthesizer: Synthesizer
    engine: Engine
    data_dir: Path

    def drain(self) -> int:
        services = self.client.app.state.services  # pyright: ignore[reportAttributeAccessIssue]
        return int(services.runner.run_pending())

    def upload(self, attempt_id: str, text: str) -> str:
        clip = self.synthesizer.synthesize(text)
        wav = (self.data_dir / clip.path).read_bytes()
        response = self.client.post(
            f"/api/attempts/{attempt_id}/recording",
            content=wav,
            headers={"content-type": "audio/wav"},
        )
        assert response.status_code == 202, response.text
        job_id: str = response.json()["job_id"]
        return job_id
