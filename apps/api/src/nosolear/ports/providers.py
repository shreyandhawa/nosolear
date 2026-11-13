"""Provider ports: what the job steps and the composition root see of a speech or coach service.

Adapters implement these in `adapters/`; wrappers (retry, metered, cache) implement them too and
hold the next layer as `.inner`. `wav` is always an absolute path to a 16 kHz mono 16-bit WAV
under the data dir. `Synthesizer` is the cached port callers use; `SpeechSynthesizer` is the raw
call beneath it.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from nosolear.domain.coach import CoachAnalysis, CoachExplanation, CoachTask
from nosolear.domain.speech import (
    PhoneProbeResult,
    PronunciationAssessment,
    ProviderCapabilities,
    SynthesizedAudio,
    SynthesizedClip,
    Transcript,
)


class PronunciationScorer(Protocol):
    def score(self, wav: Path, *, reference_text: str | None) -> PronunciationAssessment: ...


class Transcriber(Protocol):
    def transcribe(self, wav: Path) -> Transcript: ...


class PhoneProbe(Protocol):
    def probe(self, wav: Path, *, reference_text: str) -> PhoneProbeResult: ...


class SpeechSynthesizer(Protocol):
    """The raw, retry and metered layer. Returns the audio and the characters actually billed."""

    def synthesize(self, text: str, *, rate_percent: int) -> SynthesizedAudio: ...


class Synthesizer(Protocol):
    """The cached port callers use: returns a clip stored under `tts/<hash>.wav`."""

    def synthesize(self, text: str, *, rate_percent: int = 0) -> SynthesizedClip: ...


class Coach(Protocol):
    def analyze(
        self,
        *,
        task: CoachTask,
        prompt_text: str,
        transcript: str,
        allowed_keys: Sequence[str],
    ) -> CoachAnalysis: ...

    def explain(self, *, error_key: str, quote: str, context: str) -> CoachExplanation: ...


class CapabilityProbe(Protocol):
    @property
    def adapter(self) -> str: ...

    def probe(self) -> ProviderCapabilities: ...
