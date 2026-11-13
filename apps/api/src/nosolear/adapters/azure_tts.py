"""Azure text-to-speech: the raw `SpeechSynthesizer` (ARCHITECTURE.md section 5.2).

The configured voice is tried first. A non-retryable rejection switches, once and for the rest of
the process, to `FALLBACK_VOICE`. A rate limit or a service failure is not a voice problem, so it
is raised as it is. Billing is the SSML length of every request sent, fallback included.
"""

from nosolear.adapters.azure_speech import AzureSpeech, wav_duration_ms
from nosolear.adapters.azure_speech import WordBoundary as _Boundary
from nosolear.domain.errors import ProviderUnavailable, RequestNotSent, RetryableProviderError
from nosolear.domain.speech import SynthesizedAudio, WordTiming
from nosolear.domain.ssml import FALLBACK_VOICE, build_ssml

TICKS_PER_MS = 10_000
ADAPTER = "azure_tts"
ADAPTER_VERSION = 1


def _timing(boundary: _Boundary) -> WordTiming:
    start = boundary.offset_ticks // TICKS_PER_MS
    end = (boundary.offset_ticks + boundary.duration_ticks) // TICKS_PER_MS
    return WordTiming(text=boundary.text, start_ms=start, end_ms=end)


class AzureTts:
    layer = "raw"

    def __init__(self, speech: AzureSpeech, *, voice: str, locale: str) -> None:
        build_ssml("validate", voice=voice, locale=locale)  # raises ValueError on a bad setting
        self._speech = speech
        self._configured_voice = voice
        self._locale = locale
        self._on_fallback = False

    @property
    def _voice(self) -> str:
        return FALLBACK_VOICE if self._on_fallback else self._configured_voice

    def synthesize(self, text: str, *, rate_percent: int) -> SynthesizedAudio:
        billed = 0
        voice = self._voice
        ssml = build_ssml(text, voice=voice, locale=self._locale, rate_percent=rate_percent)
        billed += len(ssml)
        try:
            outcome = self._speech.synthesize(ssml)
        except RequestNotSent, RetryableProviderError:
            raise
        except ProviderUnavailable:
            if voice == FALLBACK_VOICE:
                raise
            self._on_fallback = True
            voice = FALLBACK_VOICE
            ssml = build_ssml(text, voice=voice, locale=self._locale, rate_percent=rate_percent)
            billed += len(ssml)
            outcome = self._speech.synthesize(ssml)
        wav_duration_ms(outcome.audio)  # refuses audio that is not 16 kHz mono 16-bit
        return SynthesizedAudio(
            wav=outcome.audio,
            word_timings=tuple(_timing(b) for b in outcome.word_boundaries),
            voice=voice,
            billed_chars=billed,
        )
