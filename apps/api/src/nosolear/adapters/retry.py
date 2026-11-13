"""Retry for paid provider calls (ARCHITECTURE.md section 8.1).

Only `RetryableProviderError` (429, 5xx, 529, connection errors and timeouts) is retried, after
1, 2, 4 and 8 seconds: five attempts in all. Then the caller gets a plain `ProviderUnavailable`
with the last safe message. `CapExceeded`, `RequestNotSent` and every other error pass straight
through. Sleeps are injected so tests never really wait.
"""

import time
from collections.abc import Callable, Sequence
from pathlib import Path

from nosolear.budget.compose import PortWrapper
from nosolear.domain.coach import CoachAnalysis, CoachExplanation, CoachTask
from nosolear.domain.errors import ProviderUnavailable, RetryableProviderError
from nosolear.domain.speech import PronunciationAssessment, SynthesizedAudio, Transcript
from nosolear.ports.providers import Coach, PronunciationScorer, SpeechSynthesizer, Transcriber

BACKOFF_SECONDS: tuple[int, ...] = (1, 2, 4, 8)

Sleep = Callable[[float], None]


def retry_call[T](call: Callable[[], T], *, sleep: Sleep = time.sleep) -> T:
    for delay in BACKOFF_SECONDS:
        try:
            return call()
        except RetryableProviderError:
            sleep(delay)
    try:
        return call()
    except RetryableProviderError as last:
        raise ProviderUnavailable(last.safe_message) from None


class RetryingPronunciationScorer(PortWrapper[PronunciationScorer]):
    layer = "retry"

    def __init__(self, inner: PronunciationScorer, *, sleep: Sleep = time.sleep) -> None:
        super().__init__(inner)
        self._sleep = sleep

    def score(self, wav: Path, *, reference_text: str | None) -> PronunciationAssessment:
        return retry_call(
            lambda: self.inner.score(wav, reference_text=reference_text), sleep=self._sleep
        )


class RetryingTranscriber(PortWrapper[Transcriber]):
    layer = "retry"

    def __init__(self, inner: Transcriber, *, sleep: Sleep = time.sleep) -> None:
        super().__init__(inner)
        self._sleep = sleep

    def transcribe(self, wav: Path) -> Transcript:
        return retry_call(lambda: self.inner.transcribe(wav), sleep=self._sleep)


class RetryingSpeechSynthesizer(PortWrapper[SpeechSynthesizer]):
    layer = "retry"

    def __init__(self, inner: SpeechSynthesizer, *, sleep: Sleep = time.sleep) -> None:
        super().__init__(inner)
        self._sleep = sleep

    def synthesize(self, text: str, *, rate_percent: int) -> SynthesizedAudio:
        return retry_call(
            lambda: self.inner.synthesize(text, rate_percent=rate_percent), sleep=self._sleep
        )


class RetryingCoach(PortWrapper[Coach]):
    layer = "retry"

    def __init__(self, inner: Coach, *, sleep: Sleep = time.sleep) -> None:
        super().__init__(inner)
        self._sleep = sleep

    def analyze(
        self,
        *,
        task: CoachTask,
        prompt_text: str,
        transcript: str,
        allowed_keys: Sequence[str],
    ) -> CoachAnalysis:
        return retry_call(
            lambda: self.inner.analyze(
                task=task,
                prompt_text=prompt_text,
                transcript=transcript,
                allowed_keys=allowed_keys,
            ),
            sleep=self._sleep,
        )

    def explain(self, *, error_key: str, quote: str, context: str) -> CoachExplanation:
        return retry_call(
            lambda: self.inner.explain(error_key=error_key, quote=quote, context=context),
            sleep=self._sleep,
        )
