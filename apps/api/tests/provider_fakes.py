"""In-memory stand-ins for the provider ports. Import as `from provider_fakes import ...`.

Every fake is a raw layer (`layer = "raw"`). Queued `errors` raise first, one per call; then the
queued `results` are returned in order, and the last one repeats. Every call's arguments are kept
in `.calls` as a tuple in signature order, so tests can assert what was sent.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wavs import make_wav

from nosolear.domain.budget import Provider
from nosolear.domain.coach import CoachAnalysis, CoachExplanation, CoachTask
from nosolear.domain.speech import (
    PhoneProbeResult,
    PronunciationAssessment,
    ProviderCapabilities,
    RawResult,
    ScoringMode,
    SynthesizedAudio,
    SynthesizedClip,
    Transcript,
)

TTS_DIR = "tts"


class _Script[R]:
    def __init__(self, results: Sequence[R], errors: Sequence[Exception]) -> None:
        self._results = list(results)
        self._errors = list(errors)

    def next(self) -> R:
        if self._errors:
            raise self._errors.pop(0)
        if not self._results:
            raise RuntimeError("the fake has no result queued")
        if len(self._results) == 1:
            return self._results[0]
        return self._results.pop(0)


def raw_result(
    adapter: str = "fake",
    payload: Mapping[str, object] | None = None,
    provider_version: str = "fake",
    provider: str = Provider.AZURE.value,
) -> RawResult:
    return RawResult(
        provider=provider,
        provider_version=provider_version,
        adapter=adapter,
        adapter_version=1,
        payload=dict(payload) if payload is not None else {},
    )


def assessment(**overrides: Any) -> PronunciationAssessment:
    base = PronunciationAssessment(
        mode=ScoringMode.SCRIPTED,
        words=(),
        accuracy=None,
        fluency=None,
        completeness=None,
        prosody=None,
        has_nbest=False,
        has_prosody=False,
        raw=raw_result(adapter="azure_pa"),
    )
    return replace(base, **overrides)


def transcript(text: str, **overrides: Any) -> Transcript:
    base = Transcript(text=text, words=(), fillers_kept=False, raw=raw_result(adapter="azure_stt"))
    return replace(base, **overrides)


class FakeScorer:
    layer = "raw"
    calls: list[tuple[Path, str | None]]

    def __init__(
        self,
        results: Sequence[PronunciationAssessment] = (),
        errors: Sequence[Exception] = (),
    ) -> None:
        self._script: _Script[PronunciationAssessment] = _Script(results, errors)
        self.calls = []

    def score(self, wav: Path, *, reference_text: str | None) -> PronunciationAssessment:
        self.calls.append((wav, reference_text))
        return self._script.next()


class FakeTranscriber:
    layer = "raw"
    calls: list[tuple[Path]]

    def __init__(
        self, results: Sequence[Transcript] = (), errors: Sequence[Exception] = ()
    ) -> None:
        self._script: _Script[Transcript] = _Script(results, errors)
        self.calls = []

    def transcribe(self, wav: Path) -> Transcript:
        self.calls.append((wav,))
        return self._script.next()


class FakePhoneProbe:
    layer = "raw"
    calls: list[tuple[Path, str]]

    def __init__(
        self, results: Sequence[PhoneProbeResult] = (), errors: Sequence[Exception] = ()
    ) -> None:
        self._script: _Script[PhoneProbeResult] = _Script(results, errors)
        self.calls = []

    def probe(self, wav: Path, *, reference_text: str) -> PhoneProbeResult:
        self.calls.append((wav, reference_text))
        return self._script.next()


class FakeSpeechSynthesizer:
    layer = "raw"
    calls: list[tuple[str, int]]

    def __init__(
        self, results: Sequence[SynthesizedAudio] = (), errors: Sequence[Exception] = ()
    ) -> None:
        self._script: _Script[SynthesizedAudio] = _Script(results, errors)
        self.calls = []

    def synthesize(self, text: str, *, rate_percent: int) -> SynthesizedAudio:
        self.calls.append((text, rate_percent))
        return self._script.next()


class FakeSynthesizer:
    """The cached port: writes a silent WAV at `tts/<sha256(text)>.wav` under `data_dir`."""

    layer = "raw"
    calls: list[tuple[str, int]]

    def __init__(self, data_dir: Path, *, duration_ms: int = 1000) -> None:
        self._data_dir = data_dir
        self._duration_ms = duration_ms
        self.calls = []

    def synthesize(self, text: str, *, rate_percent: int = 0) -> SynthesizedClip:
        self.calls.append((text, rate_percent))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        target = self._data_dir / TTS_DIR / f"{digest}.wav"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(make_wav(self._duration_ms / 1000, freq=None))
        return SynthesizedClip(
            hash=digest,
            path=f"{TTS_DIR}/{digest}.wav",
            voice="en-US-AvaNeural",
            rate_percent=rate_percent,
            word_timings=(),
            duration_ms=self._duration_ms,
        )


class FakeCoach:
    """`analyze` and `explain` have their own queues; `errors` is shared by both."""

    layer = "raw"
    calls: list[tuple[CoachTask, str, str, tuple[str, ...]]]
    explain_calls: list[tuple[str, str, str]]

    def __init__(
        self,
        results: Sequence[CoachAnalysis] = (),
        errors: Sequence[Exception] = (),
        explain_results: Sequence[CoachExplanation] = (),
    ) -> None:
        self._analyses: _Script[CoachAnalysis] = _Script(results, errors)
        self._explanations: _Script[CoachExplanation] = _Script(explain_results, ())
        self.calls = []
        self.explain_calls = []

    def analyze(
        self,
        *,
        task: CoachTask,
        prompt_text: str,
        transcript: str,
        allowed_keys: Sequence[str],
    ) -> CoachAnalysis:
        self.calls.append((task, prompt_text, transcript, tuple(allowed_keys)))
        return self._analyses.next()

    def explain(self, *, error_key: str, quote: str, context: str) -> CoachExplanation:
        self.explain_calls.append((error_key, quote, context))
        return self._explanations.next()


class FakeCapabilityProbe:
    layer = "raw"
    calls: int

    def __init__(
        self, results: Sequence[ProviderCapabilities] = (), errors: Sequence[Exception] = ()
    ) -> None:
        self._script: _Script[ProviderCapabilities] = _Script(results, errors)
        self.calls = 0

    @property
    def adapter(self) -> str:
        return "fake"

    def probe(self) -> ProviderCapabilities:
        self.calls += 1
        return self._script.next()


def probed_at() -> datetime:
    return datetime(2026, 11, 13, 9, 0, tzinfo=UTC)


def wrapper_chain(port: object) -> list[type]:
    """The classes along `.inner`, outermost first: the typed twin of 0c's `layers_of`."""
    chain: list[type] = []
    current: Any = port
    while True:
        chain.append(type(current))
        if not hasattr(current, "inner"):
            return chain
        current = current.inner
