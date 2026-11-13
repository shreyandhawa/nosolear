"""Provider surfaces that carry the planted keys: the errors each paid adapter raises, and the
stored steps of an analyze job that ran over failing adapters (ARCHITECTURE.md section 16)."""

import logging
import traceback
from datetime import UTC, datetime
from pathlib import Path

import anthropic
import httpx2
from factories import FixedClock, make_settings
from provider_fakes import FakeSpeechBackend, FakeTranscriber
from pydantic import SecretStr
from sqlalchemy import text
from wavs import write_wav

from nosolear.adapters.azure_pa import AzurePronunciationScorer
from nosolear.adapters.azure_speech import AzureSpeech, Cancellation
from nosolear.adapters.claude_coach import ClaudeCoach
from nosolear.api.deps import RawPorts, build_services
from nosolear.app.run_job import run_job
from nosolear.domain.coach import CoachTask, coach_keys
from nosolear.domain.errors import ProviderUnavailable
from nosolear.domain.jobs import JobKind
from nosolear.domain.speech import RawResult, Transcript
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.persistence.repositories import AttemptRepository, RecordingRepository
from nosolear.ports.audio import NewRecording, StoredRecording
from security.planted import (
    FORMAT,
    PLANTED_ANTHROPIC_KEY,
    PLANTED_AZURE_KEY,
    PROVIDER_BODY_MARKER,
    LogCapture,
    leak_surface,
)

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
_BODY = f"invalid x-api-key {PLANTED_ANTHROPIC_KEY} {PROVIDER_BODY_MARKER}"


def _claude_rejecting(api_key: str) -> ClaudeCoach:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            401, json={"type": "error", "error": {"type": "authentication_error", "message": _BODY}}
        )

    http = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    return ClaudeCoach(
        api_key=SecretStr(api_key),
        model="claude-opus-5-5",
        taxonomy=DEFAULT_TAXONOMY,
        http_client=http,
    )


def _azure_rejecting() -> AzureSpeech:
    details = f"bad {PLANTED_AZURE_KEY} {PLANTED_ANTHROPIC_KEY} {PROVIDER_BODY_MARKER}"
    backend = FakeSpeechBackend(cancel=Cancellation("AuthenticationFailure", details))
    return AzureSpeech(key=SecretStr(PLANTED_AZURE_KEY), region="eastus", backend=backend)


@leak_surface
def adapter_error_paths(tmp: Path) -> tuple[str, str]:
    """Each paid adapter's rejection, with its traceback: Claude answers 401 with a body that
    echoes the key, and Azure cancels with details that hold both keys and the body marker."""
    rendered: list[str] = []
    coach = _claude_rejecting(PLANTED_ANTHROPIC_KEY)
    try:
        coach.analyze(
            task=CoachTask.QUICK_ANSWERS,
            prompt_text="Why?",
            transcript="I go",
            allowed_keys=coach_keys(DEFAULT_TAXONOMY, CoachTask.QUICK_ANSWERS),
        )
    except ProviderUnavailable as exc:
        rendered.append(str(exc) + repr(exc) + "".join(traceback.format_exception(exc)))
    else:
        raise AssertionError("a rejected key did not raise")
    scorer = AzurePronunciationScorer(_azure_rejecting(), locale="en-US")
    wav = write_wav(tmp / "adapter.wav", 1.0)
    try:
        scorer.score(wav, reference_text=None)
    except ProviderUnavailable as exc:
        rendered.append(str(exc) + repr(exc) + "".join(traceback.format_exception(exc)))
    else:
        raise AssertionError("a cancelled request did not raise")
    return "paid adapter error paths and tracebacks", "\n".join(rendered)


def _spoken(text_value: str) -> Transcript:
    payload: dict[str, object] = {
        "results": [{"RecognitionStatus": "Success", "DisplayText": text_value}]
    }
    raw = RawResult(
        provider="azure",
        provider_version="fake-sdk",
        adapter="azure_stt",
        adapter_version=1,
        payload=payload,
    )
    return Transcript(text=text_value, words=(), fillers_kept=False, raw=raw)


@leak_surface
def job_steps_json(tmp: Path) -> tuple[str, str]:
    """One analyze job over a failing scorer and a rejecting coach: the stored steps_json, the
    job's repr and the runner log. The safe messages must be there, and no key."""
    settings = make_settings(data_dir=tmp, azure_speech_region="eastus")
    engine = create_engine_for(settings.database_url)
    upgrade_to_head(engine)
    clock = FixedClock(NOW)
    try:
        services = build_services(
            settings,
            engine,
            registry=None,
            clock=clock,
            raw_ports=RawPorts(
                scorer=AzurePronunciationScorer(_azure_rejecting(), locale="en-US"),
                transcriber=FakeTranscriber(results=[_spoken("I go to the market")]),
                coach=_claude_rejecting(PLANTED_ANTHROPIC_KEY),
            ),
        )
        attempt_id = AttemptRepository(engine).create_attempt(
            session_kind="daily", step="speak", reference_text=None, scripted=False, now=NOW
        )
        relative = f"recordings/{'0' * 8}-0000-4000-8000-{'0' * 12}.wav"
        write_wav(tmp / relative, 1.0)
        stored = StoredRecording(
            path=relative, duration_ms=1000, sample_rate=16000, sha256="0" * 64
        )
        _, job = RecordingRepository(engine, clock).add_and_enqueue(
            NewRecording(attempt_id=attempt_id, stored=stored)
        )
        with LogCapture(logging.Formatter(FORMAT), "nosolear.app.run_job") as cap:
            finished = run_job(job_id=job.id, jobs=services.jobs, registry=services.registry)
        with engine.connect() as conn:
            steps_json = conn.execute(
                text("SELECT steps_json FROM jobs WHERE id = :id"), {"id": job.id}
            ).scalar_one()
    finally:
        engine.dispose()
    assert finished.kind is JobKind.ANALYZE
    assert "Anthropic rejected the API key" in steps_json, "the coach's safe message is missing"
    assert "Azure Speech rejected the key" in steps_json, "the scorer's safe message is missing"
    return "analyze job steps_json, job repr and run_job log", "\n".join(
        [steps_json, repr(finished), cap.text]
    )
