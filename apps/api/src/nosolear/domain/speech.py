"""Speech provider results: the typed shapes every adapter returns. Pure: no I/O.

`RawResult.payload` is stored unchanged as `analyses.raw_json`, so 0e can re-extract fields from
what was stored without calling the provider again. That is why it is a plain mapping, not a
typed record: the typed parts below are derived from it, and the raw copy is the source of truth.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from nosolear.domain.analyses import AnalysisKind, NewAnalysis, StoredAnalysis

LOCAL = "local"
"""The provider id for on-machine models. Azure and Anthropic use `Provider` values."""

MAX_SCRIPTED_SECONDS = 30


@dataclass(frozen=True, slots=True)
class RawResult:
    provider: str
    provider_version: str
    adapter: str
    adapter_version: int
    payload: Mapping[str, object]


def new_analysis(attempt_id: str, kind: AnalysisKind, raw: RawResult) -> NewAnalysis:
    return NewAnalysis(
        attempt_id=attempt_id,
        kind=kind,
        provider=raw.provider,
        provider_version=raw.provider_version,
        adapter=raw.adapter,
        adapter_version=raw.adapter_version,
        raw=raw.payload,
    )


def raw_result_of(stored: StoredAnalysis) -> RawResult:
    return RawResult(
        provider=stored.provider,
        provider_version=stored.provider_version,
        adapter=stored.adapter,
        adapter_version=stored.adapter_version,
        payload=stored.raw,
    )


@dataclass(frozen=True, slots=True)
class WordTiming:
    text: str
    start_ms: int
    end_ms: int
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.start_ms <= self.end_ms:
            raise ValueError("a word timing needs 0 <= start_ms <= end_ms")


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    words: tuple[WordTiming, ...]
    fillers_kept: bool
    raw: RawResult


@dataclass(frozen=True, slots=True)
class NBestPhoneme:
    phoneme: str
    score: float


@dataclass(frozen=True, slots=True)
class PhonemeAssessment:
    phoneme: str
    accuracy: float
    nbest: tuple[NBestPhoneme, ...]
    start_ms: int | None
    end_ms: int | None


@dataclass(frozen=True, slots=True)
class ProsodyFeedback:
    """`error_types` holds Azure's `ErrorTypes` verbatim: UnexpectedBreak, MissingBreak and
    Monotone."""

    error_types: tuple[str, ...]
    unexpected_break: float | None
    missing_break: float | None
    monotone: float | None


@dataclass(frozen=True, slots=True)
class WordAssessment:
    word: str
    accuracy: float | None
    error_type: str
    start_ms: int | None
    end_ms: int | None
    phonemes: tuple[PhonemeAssessment, ...]
    prosody: ProsodyFeedback | None


class ScoringMode(StrEnum):
    SCRIPTED = "scripted"
    CONTINUOUS = "continuous"
    UNSCRIPTED = "unscripted"


FREE_TALK_SCORING = ScoringMode.UNSCRIPTED
"""Provisional: the live comparison in Task 5 picks unscripted or transcribe-then-score (§4)."""


@dataclass(frozen=True, slots=True)
class PronunciationAssessment:
    mode: ScoringMode
    words: tuple[WordAssessment, ...]
    accuracy: float | None
    fluency: float | None
    completeness: float | None
    prosody: float | None
    has_nbest: bool
    has_prosody: bool
    raw: RawResult


@dataclass(frozen=True, slots=True)
class PhoneProbeResult:
    expected_words: tuple[tuple[str, ...], ...]
    heard: tuple[str, ...]
    raw: RawResult

    @property
    def expected(self) -> tuple[str, ...]:
        return tuple(phoneme for word in self.expected_words for phoneme in word)


@dataclass(frozen=True, slots=True)
class SynthesizedAudio:
    wav: bytes
    word_timings: tuple[WordTiming, ...]
    voice: str
    billed_chars: int


@dataclass(frozen=True, slots=True)
class SynthesizedClip:
    hash: str
    path: str
    """Relative to the data dir; always `tts/<hash>.wav`."""
    voice: str
    rate_percent: int
    word_timings: tuple[WordTiming, ...]
    duration_ms: int


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    provider: str
    adapter: str
    adapter_version: int
    provider_version: str
    region: str | None
    locale: str | None
    capabilities: Mapping[str, object]
    probed_at: datetime
