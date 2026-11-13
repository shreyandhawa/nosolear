"""Typed domain errors shared by the job runner and the API.

Every message is a literal sentence written in Nosolear's code. Never build one from provider
text, input bytes, header values or a key.
"""

from __future__ import annotations

from typing import ClassVar, Literal

AudioReason = Literal[
    "too_large",
    "too_long",
    "empty",
    "not_wav",
    "bad_chunks",
    "unsupported_format",
    "bad_sample_rate",
    "bad_content_type",
]


class NosolearError(ValueError):
    code: ClassVar[str] = "error"
    default_message: ClassVar[str] = "Something went wrong."

    def __init__(self, message: str | None = None) -> None:
        self._message = message
        super().__init__(self.safe_message)

    @property
    def safe_message(self) -> str:
        return self._message if self._message is not None else self.default_message

    def __str__(self) -> str:
        return self.safe_message


_AUDIO_MESSAGES: dict[AudioReason, str] = {
    "too_large": "The recording is larger than the 10 MB upload limit.",
    "too_long": "The recording is longer than the 120 second limit.",
    "empty": "The recording contains no audio.",
    "not_wav": "The upload is not a WAV file.",
    "bad_chunks": "The WAV file must contain exactly one fmt chunk and one data chunk.",
    "unsupported_format": "The WAV file must be 16-bit PCM, mono.",
    "bad_sample_rate": (
        "The WAV sample rate must be one of 16000, 22050, 24000, 32000, 44100 or 48000 Hz."
    ),
    "bad_content_type": "The upload must be sent as audio/wav.",
}


class InvalidAudio(NosolearError):
    code: ClassVar[str] = "invalid_audio"
    default_message: ClassVar[str] = "The recording is not valid audio."

    def __init__(self, reason: AudioReason) -> None:
        self.reason: AudioReason = reason
        super().__init__(_AUDIO_MESSAGES[reason])


class CapExceeded(NosolearError):
    code: ClassVar[str] = "cap_exceeded"
    default_message: ClassVar[str] = "The usage cap for this period would be exceeded."


class ProviderUnavailable(NosolearError):
    code: ClassVar[str] = "provider_unavailable"
    default_message: ClassVar[str] = "The speech or language provider is unavailable."


class CapabilityMissing(NosolearError):
    code: ClassVar[str] = "capability_missing"
    default_message: ClassVar[str] = "This capability is not available in the current setup."


class RequestNotSent(ProviderUnavailable):
    """Raised by a raw adapter that failed before any request left the machine."""

    default_message: ClassVar[str] = "The request was not sent to the provider."


class RetryableProviderError(ProviderUnavailable):
    """A provider failure worth retrying: 429, 5xx, 529, connection errors and timeouts.

    The retry wrapper turns it into a plain `ProviderUnavailable` once its attempts run out.
    """


class MalformedProviderResponse(ProviderUnavailable):
    """A provider answered, but the answer does not match the schema we asked for."""
