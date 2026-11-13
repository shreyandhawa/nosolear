"""The one client for Azure Speech, shared by the three Azure adapters (ARCHITECTURE.md section 5).

Only this module imports `azure.cognitiveservices.speech`, and only inside method bodies, so the
base import never loads the SDK. One request is in flight per process: a module-level lock guards
every backend call, because the free tier allows one concurrent request. A missing key or region
raises `RequestNotSent` before anything is sent. A cancellation from the service goes through
`classify`, whose message is a literal sentence; the cancellation details never leave this module.
"""

import io
import json
import re
import threading
import wave
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Protocol, cast

from pydantic import SecretStr

from nosolear.domain.errors import (
    MalformedProviderResponse,
    ProviderUnavailable,
    RequestNotSent,
    RetryableProviderError,
)

SDK_DISTRIBUTION = "azure-cognitiveservices-speech"
TICKS_PER_SECOND = 10_000_000
NOT_CONFIGURED = (
    "Azure Speech isn't configured: set NOSOLEAR_AZURE_SPEECH_KEY and "
    "NOSOLEAR_AZURE_SPEECH_REGION in .env"
)
_REGION = re.compile(r"[a-z0-9]+")
_SERVICE_LOCK = threading.Lock()
_RETRYABLE_CODES = frozenset(
    {"ServiceError", "ServiceTimeout", "ConnectionFailure", "ServiceUnavailable"}
)
_KEY_CODES = frozenset({"AuthenticationFailure", "Forbidden"})


@dataclass(frozen=True, slots=True)
class Cancellation:
    code: str
    """The SDK's `CancellationErrorCode` member name, such as `TooManyRequests`."""
    details: str
    """Provider text. Used only by `classify`, never surfaced."""


@dataclass(frozen=True, slots=True)
class RecognitionRequest:
    wav: Path
    locale: str
    continuous: bool
    pronunciation_json: str | None
    word_timestamps: bool
    timeout_s: float


@dataclass(frozen=True, slots=True)
class RecognitionOutcome:
    results: tuple[Mapping[str, object], ...]
    """One parsed `SpeechServiceResponse_JsonResult` per recognized phrase."""
    cancellation: Cancellation | None


@dataclass(frozen=True, slots=True)
class WordBoundary:
    """A word boundary as the service reports it: 100 ns ticks, not milliseconds."""

    text: str
    offset_ticks: int
    duration_ticks: int


@dataclass(frozen=True, slots=True)
class SynthesisOutcome:
    audio: bytes
    word_boundaries: tuple[WordBoundary, ...]
    cancellation: Cancellation | None


class SpeechBackend(Protocol):
    @property
    def version(self) -> str: ...

    def recognize(self, request: RecognitionRequest) -> RecognitionOutcome: ...

    def synthesize(self, ssml: str) -> SynthesisOutcome: ...


def sdk_version() -> str:
    return metadata.version(SDK_DISTRIBUTION)


def classify(cancellation: Cancellation) -> ProviderUnavailable:
    """The error a cancellation maps to. Retryable ones are 429 and 5xx-style service failures."""
    if cancellation.code == "TooManyRequests" or "429" in cancellation.details:
        return RetryableProviderError("Azure Speech is rate-limiting requests")
    if cancellation.code in _RETRYABLE_CODES:
        return RetryableProviderError("Azure Speech is unavailable")
    if cancellation.code in _KEY_CODES:
        return ProviderUnavailable(
            "Azure Speech rejected the key or region; check NOSOLEAR_AZURE_SPEECH_KEY and "
            "NOSOLEAR_AZURE_SPEECH_REGION"
        )
    if cancellation.code == "BadRequest":
        return ProviderUnavailable("Azure Speech rejected the request")
    return ProviderUnavailable("Azure Speech failed")


class AzureSpeech:
    """The shared client. `backend=None` means the real SDK, built per call from the settings."""

    def __init__(
        self,
        *,
        key: SecretStr | None,
        region: str | None,
        backend: SpeechBackend | None = None,
    ) -> None:
        if region is not None and not _REGION.fullmatch(region):
            raise ValueError(
                "the Azure region must be lowercase letters and digits, such as eastus"
            )
        self._key = key
        self._region = region
        self._backend = backend

    @property
    def version(self) -> str:
        return self._backend.version if self._backend is not None else sdk_version()

    def recognize(self, request: RecognitionRequest) -> RecognitionOutcome:
        backend = self._ready()
        with _SERVICE_LOCK:
            outcome = backend.recognize(request)
        if outcome.cancellation is not None:
            raise classify(outcome.cancellation) from None
        return outcome

    def synthesize(self, ssml: str) -> SynthesisOutcome:
        backend = self._ready()
        with _SERVICE_LOCK:
            outcome = backend.synthesize(ssml)
        if outcome.cancellation is not None:
            raise classify(outcome.cancellation) from None
        return outcome

    def _ready(self) -> SpeechBackend:
        if self._key is None or self._region is None:
            raise RequestNotSent(NOT_CONFIGURED)
        if self._backend is not None:
            return self._backend
        return SdkSpeechBackend(key=self._key, region=self._region)


def _json_result(text: str) -> Mapping[str, object]:
    """One phrase's detailed JSON. A recognition with no JSON is a no-match, not an error."""
    if not text:
        return {"RecognitionStatus": "NoMatch"}
    try:
        parsed: object = json.loads(text)
    except json.JSONDecodeError:
        raise MalformedProviderResponse("Azure returned a result Nosolear can't read") from None
    if not isinstance(parsed, dict):
        raise MalformedProviderResponse("Azure returned a result Nosolear can't read")
    return cast("dict[str, object]", parsed)


def _sdk() -> Any:
    """The SDK module, imported on first use. The SDK ships no type stubs, so it is typed `Any`
    here, once, and the rest of this module never sees its unknown types."""
    import azure.cognitiveservices.speech as speechsdk  # pyright: ignore[reportMissingTypeStubs]

    return speechsdk


class SdkSpeechBackend:
    """The only code that touches the SDK. Each method loads it lazily through `_sdk()`."""

    def __init__(self, *, key: SecretStr, region: str) -> None:
        self._key = key
        self._region = region

    @property
    def version(self) -> str:
        return sdk_version()

    def synthesize(self, ssml: str) -> SynthesisOutcome:
        speechsdk = _sdk()

        config = speechsdk.SpeechConfig(
            subscription=self._key.get_secret_value(), region=self._region
        )
        config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm
        )
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=config, audio_config=None)
        boundaries: list[WordBoundary] = []

        def on_boundary(event: Any) -> None:
            if event.boundary_type == speechsdk.SpeechSynthesisBoundaryType.Word:
                ticks = round(event.duration.total_seconds() * TICKS_PER_SECOND)
                boundaries.append(WordBoundary(event.text, event.audio_offset, ticks))

        synthesizer.synthesis_word_boundary.connect(on_boundary)
        result = synthesizer.speak_ssml_async(ssml).get()
        bounds = tuple(boundaries)
        if result.reason == speechsdk.ResultReason.Canceled:
            details = speechsdk.SpeechSynthesisCancellationDetails(result)
            cancelled = Cancellation(details.error_code.name, details.error_details or "")
            return SynthesisOutcome(audio=b"", word_boundaries=bounds, cancellation=cancelled)
        return SynthesisOutcome(audio=result.audio_data, word_boundaries=bounds, cancellation=None)

    def recognize(self, request: RecognitionRequest) -> RecognitionOutcome:
        speechsdk = _sdk()

        config = speechsdk.SpeechConfig(
            subscription=self._key.get_secret_value(), region=self._region
        )
        config.speech_recognition_language = request.locale
        config.output_format = speechsdk.OutputFormat.Detailed
        config.set_profanity(speechsdk.ProfanityOption.Raw)
        if request.word_timestamps:
            config.request_word_level_timestamps()
        audio = speechsdk.audio.AudioConfig(filename=str(request.wav))
        recognizer = speechsdk.SpeechRecognizer(speech_config=config, audio_config=audio)
        if request.pronunciation_json is not None:
            pronunciation = speechsdk.PronunciationAssessmentConfig(
                json_string=request.pronunciation_json
            )
            pronunciation.apply_to(recognizer)

        def json_text(result: Any) -> str:
            return result.properties.get_property(
                speechsdk.PropertyId.SpeechServiceResponse_JsonResult
            )

        def cancellation_of(result: Any) -> Cancellation | None:
            if result.reason != speechsdk.ResultReason.Canceled:
                return None
            details = speechsdk.CancellationDetails(result)
            if details.reason != speechsdk.CancellationReason.Error:
                return None
            return Cancellation(details.error_code.name, details.error_details or "")

        if not request.continuous:
            once = recognizer.recognize_once()
            cancelled = cancellation_of(once)
            if cancelled is not None:
                return RecognitionOutcome(results=(), cancellation=cancelled)
            return RecognitionOutcome(results=(_json_result(json_text(once)),), cancellation=None)

        results: list[Mapping[str, object]] = []
        problems: list[Cancellation] = []
        finished = threading.Event()

        def on_recognized(event: Any) -> None:
            if event.result.reason in (
                speechsdk.ResultReason.RecognizedSpeech,
                speechsdk.ResultReason.NoMatch,
            ):
                results.append(_json_result(json_text(event.result)))

        def on_canceled(event: Any) -> None:
            found = cancellation_of(event.result)
            if found is not None:
                problems.append(found)
            finished.set()

        recognizer.recognized.connect(on_recognized)
        recognizer.canceled.connect(on_canceled)

        def on_session_stopped(_event: Any) -> None:
            finished.set()

        recognizer.session_stopped.connect(on_session_stopped)
        recognizer.start_continuous_recognition()
        try:
            done = finished.wait(request.timeout_s)
        finally:
            recognizer.stop_continuous_recognition()
        if not done:
            problems.append(Cancellation("ServiceTimeout", ""))
        return RecognitionOutcome(
            results=tuple(results), cancellation=problems[0] if problems else None
        )


def wav_duration_ms(audio: bytes) -> int:
    """Duration of a RIFF 16 kHz mono 16-bit WAV in whole milliseconds; anything else is refused."""
    try:
        with wave.open(io.BytesIO(audio), "rb") as reader:
            shape = (reader.getframerate(), reader.getnchannels(), reader.getsampwidth())
            frames = reader.getnframes()
    except wave.Error, EOFError:
        raise MalformedProviderResponse("Azure returned audio Nosolear can't use") from None
    if shape != (16000, 1, 2):
        raise MalformedProviderResponse("Azure returned audio Nosolear can't use")
    return frames * 1000 // shape[0]
