"""The metered layer for the Azure speech ports: reserve audio seconds before the call, record
the same amount after it (ARCHITECTURE.md section 11). The estimate is the input's duration, which
is exactly what Azure bills, so the actual equals the estimate."""

from collections.abc import Sequence
from pathlib import Path

from nosolear.budget.compose import PortWrapper
from nosolear.budget.estimators import audio_seconds, claude_tokens, tts_chars
from nosolear.budget.meter import Meter
from nosolear.domain.budget import Provider, Unit
from nosolear.domain.coach import (
    CoachAnalysis,
    CoachExplanation,
    CoachTask,
    analysis_request,
    explanation_request,
)
from nosolear.domain.speech import PronunciationAssessment, SynthesizedAudio, Transcript
from nosolear.domain.taxonomy import Taxonomy
from nosolear.ports.providers import Coach, PronunciationScorer, SpeechSynthesizer, Transcriber


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


class MeteredCoach(PortWrapper[Coach]):
    """Reserves the request's upper bound under Anthropic tokens, then records `tokens_used`.
    The request is built here, from the same inputs, so the estimate matches what is sent."""

    layer = "metered"

    def __init__(self, inner: Coach, meter: Meter, *, taxonomy: Taxonomy) -> None:
        super().__init__(inner)
        self._meter = meter
        self._taxonomy = taxonomy

    def analyze(
        self,
        *,
        task: CoachTask,
        prompt_text: str,
        transcript: str,
        allowed_keys: Sequence[str],
    ) -> CoachAnalysis:
        request = analysis_request(
            task=task,
            prompt_text=prompt_text,
            transcript=transcript,
            allowed_keys=allowed_keys,
            taxonomy=self._taxonomy,
        )
        return self._meter.call(
            Provider.ANTHROPIC,
            Unit.TOKENS,
            claude_tokens(request),
            lambda: self.inner.analyze(
                task=task,
                prompt_text=prompt_text,
                transcript=transcript,
                allowed_keys=allowed_keys,
            ),
            actual=lambda analysis: analysis.tokens_used,
        )

    def explain(self, *, error_key: str, quote: str, context: str) -> CoachExplanation:
        request = explanation_request(
            error_key=error_key, quote=quote, context=context, taxonomy=self._taxonomy
        )
        return self._meter.call(
            Provider.ANTHROPIC,
            Unit.TOKENS,
            claude_tokens(request),
            lambda: self.inner.explain(error_key=error_key, quote=quote, context=context),
            actual=lambda explanation: explanation.tokens_used,
        )
