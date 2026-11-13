"""Azure text-to-speech: the raw `SpeechSynthesizer` (ARCHITECTURE.md section 5.2).

The configured voice is tried first. Only a `VoiceRejected` (Azure's malformed-request answer)
falls back to `FALLBACK_VOICE`, and the process switches for good only once the fallback has been
accepted, so a failure that is not the voice's fault never changes the voice. Rate limits, service
failures, key errors and anything unclassified are raised as they are. Billing is the SSML length
of every request sent, fallback included.
"""

from nosolear.adapters.azure_speech import AzureSpeech, VoiceRejected, wav_duration_ms
from nosolear.adapters.azure_speech import WordBoundary as _Boundary
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
        except VoiceRejected:
            if voice == FALLBACK_VOICE:
                raise
            voice = FALLBACK_VOICE
            ssml = build_ssml(text, voice=voice, locale=self._locale, rate_percent=rate_percent)
            billed += len(ssml)
            outcome = self._speech.synthesize(ssml)
            self._on_fallback = True
        wav_duration_ms(outcome.audio)  # refuses audio that is not 16 kHz mono 16-bit
        return SynthesizedAudio(
            wav=outcome.audio,
            word_timings=tuple(_timing(b) for b in outcome.word_boundaries),
            voice=voice,
            billed_chars=billed,
        )
