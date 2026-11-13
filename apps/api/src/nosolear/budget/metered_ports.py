"""The metered layer for the Azure speech ports: reserve audio seconds before the call, record
the same amount after it (ARCHITECTURE.md section 11). The estimate is the input's duration, which
is exactly what Azure bills, so the actual equals the estimate."""

from pathlib import Path

from nosolear.budget.compose import PortWrapper
from nosolear.budget.estimators import audio_seconds, tts_chars
from nosolear.budget.meter import Meter
from nosolear.domain.budget import Provider, Unit
from nosolear.domain.speech import PronunciationAssessment, SynthesizedAudio, Transcript
from nosolear.ports.providers import PronunciationScorer, SpeechSynthesizer, Transcriber


class MeteredPronunciationScorer(PortWrapper[PronunciationScorer]):
    layer = "metered"

    def __init__(self, inner: PronunciationScorer, meter: Meter) -> None:
        super().__init__(inner)
        self._meter = meter

    def score(self, wav: Path, *, reference_text: str | None) -> PronunciationAssessment:
        seconds = audio_seconds(wav)
        return self._meter.call(
            Provider.AZURE,
            Unit.AUDIO_SECONDS,
            seconds,
            lambda: self.inner.score(wav, reference_text=reference_text),
            actual=lambda _: seconds,
        )


class MeteredTranscriber(PortWrapper[Transcriber]):
    layer = "metered"

    def __init__(self, inner: Transcriber, meter: Meter) -> None:
        super().__init__(inner)
        self._meter = meter

    def transcribe(self, wav: Path) -> Transcript:
        seconds = audio_seconds(wav)
        return self._meter.call(
            Provider.AZURE,
            Unit.AUDIO_SECONDS,
            seconds,
            lambda: self.inner.transcribe(wav),
            actual=lambda _: seconds,
        )


class MeteredSpeechSynthesizer(PortWrapper[SpeechSynthesizer]):
    """Reserves the SSML characters for both voices, then records what was actually sent."""

    layer = "metered"

    def __init__(self, inner: SpeechSynthesizer, meter: Meter, *, voice: str, locale: str) -> None:
        super().__init__(inner)
        self._meter = meter
        self._voice = voice
        self._locale = locale

    def synthesize(self, text: str, *, rate_percent: int) -> SynthesizedAudio:
        estimate = tts_chars(
            text, voice=self._voice, locale=self._locale, rate_percent=rate_percent
        )
        return self._meter.call(
            Provider.AZURE,
            Unit.TTS_CHARS,
            estimate,
            lambda: self.inner.synthesize(text, rate_percent=rate_percent),
            actual=lambda audio: audio.billed_chars,
        )
