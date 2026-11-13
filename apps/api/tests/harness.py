"""An app-level harness: the real app, a temporary database and the oracle voice.

Import as `from harness import Harness`; the fixtures `make_harness` and `harness` are registered
in `tests/conftest.py`.
"""

import json
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from itertools import count as id_counter
from pathlib import Path
from typing import Any, Final
from unittest.mock import patch

import pytest
from adapters.anthropic_payloads import analysis_text, message_json
from factories import T0, FixedClock, count, loopback_client, make_settings
from fastapi.testclient import TestClient
from oracle_voice import OracleVoice
from provider_fakes import FakeCoach
from sqlalchemy import Engine

from nosolear.adapters.azure_pa import ADAPTER_VERSION as AZURE_PA_VERSION
from nosolear.api.app import create_app
from nosolear.api.deps import RawPorts
from nosolear.domain.coach import CoachAnalysis, Rubric, parse_coach_analysis
from nosolear.domain.content import SeedContent
from nosolear.domain.observations import Observation
from nosolear.domain.speech import ProviderCapabilities, RawResult
from nosolear.persistence.capabilities import CapabilityRepository
from nosolear.persistence.repositories import AttemptRepository, ObservationRepository
from nosolear.ports.clock import Clock
from nosolear.ports.providers import Synthesizer

PROBE_INSTALLED: Final = "nosolear.api.deps.phone_probe_installed"
_next_id = id_counter()


def _empty_coach(rubric: Rubric | None = None) -> CoachAnalysis:
    """The coach's answer with no findings, and the rubric when one is given."""
    text = analysis_text()
    if rubric is not None:
        text = json.dumps(
            {
                "findings": [],
                "rubric": {
                    "structure": rubric.structure,
                    "clarity": rubric.clarity,
                    "concision": rubric.concision,
                },
                "rewrite": None,
            }
        )
    raw = RawResult(
        provider="anthropic",
        provider_version="oracle",
        adapter="claude_coach",
        adapter_version=1,
        payload=message_json(text),
    )
    return parse_coach_analysis(raw, transcript="", allowed_keys=())


@dataclass
class Harness:
    client: TestClient
    voice: OracleVoice
    engine: Engine
    synthesizer: Synthesizer
    clock: Clock
    data_dir: Path

    def drain(self) -> int:
        """Runs every queued job in this thread."""
        return int(self.client.app.state.services.runner.run_pending())  # pyright: ignore[reportAttributeAccessIssue]

    def upload(self, attempt_id: str, text: str) -> str:
        """Synthesizes `text` through the app's cached synthesizer and posts the clip."""
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

    def attempt(
        self,
        *,
        step: str,
        scripted: bool,
        reference_text: str | None,
        session_kind: str = "daily",
    ) -> str:
        return AttemptRepository(self.engine).create_attempt(
            session_kind=session_kind,
            step=step,
            reference_text=reference_text,
            scripted=scripted,
            now=self.clock.now(),
        )

    def observations(self) -> list[Observation]:
        return ObservationRepository(self.engine).all()

    def ledger_rows(self) -> int:
        return count(self.engine, "usage_ledger")


@pytest.fixture
def make_harness(tmp_path: Path) -> Iterator[Callable[..., Harness]]:
    """Builds a started app per call. `probe=True` lets the phone probe run. Without it the
    local probe is reported as not installed, so no model is ever loaded. `start_runner=True`
    serves tests that follow a job over HTTP."""
    stack = ExitStack()

    def build(
        *,
        probe: bool = False,
        clock: Clock | None = None,
        start_runner: bool = False,
        content: SeedContent | None = None,
        rubric: Rubric | None = None,
    ) -> Harness:
        data_dir = tmp_path / f"h{next(_next_id)}"
        voice = OracleVoice()
        clock_used: Clock = clock or FixedClock(T0)
        ports = RawPorts(
            scorer=voice.scorer,
            transcriber=voice.transcriber,
            speech_synthesizer=voice.speech_synthesizer,
            phone_probe=voice.probe if probe else None,
            coach=FakeCoach([_empty_coach(rubric)]),
        )
        app = create_app(
            make_settings(data_dir=data_dir),
            clock=clock_used,
            raw_ports=ports,
            start_runner=start_runner,
            content=content,
        )
        if not probe:
            stack.enter_context(patch(PROBE_INSTALLED, return_value=False))
        client = stack.enter_context(loopback_client(app))
        services: Any = app.state.services  # pyright: ignore[reportAttributeAccessIssue]
        # Azure's n-best and prosody probe, as a live `doctor --probe` would have stored it, so
        # the `azure_pa` detector is calibratable in every harness.
        CapabilityRepository(app.state.engine).add(  # pyright: ignore[reportAttributeAccessIssue]
            ProviderCapabilities(
                provider="azure",
                adapter="azure_pa",
                adapter_version=AZURE_PA_VERSION,
                provider_version="harness",
                region=None,
                locale="en-US",
                capabilities={"nbest_phonemes": True, "prosody": True},
                probed_at=clock_used.now(),
            )
        )
        return Harness(
            client=client,
            voice=voice,
            engine=app.state.engine,  # pyright: ignore[reportAttributeAccessIssue]
            synthesizer=services.providers.synthesizer,
            clock=clock_used,
            data_dir=data_dir,
        )

    try:
        yield build
    finally:
        stack.close()


@pytest.fixture
def harness(make_harness: Callable[..., Harness]) -> Harness:
    return make_harness()
