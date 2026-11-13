import pytest
from provider_fakes import (
    FakeCoach,
    FakeScorer,
    FakeSpeechSynthesizer,
    FakeTranscriber,
    assessment,
    transcript,
)
from security.planted import PROVIDER_BODY_MARKER, assert_no_leak

from nosolear.adapters.retry import (
    RetryingCoach,
    RetryingPronunciationScorer,
    RetryingSpeechSynthesizer,
    RetryingTranscriber,
    retry_call,
)
from nosolear.domain.coach import CoachTask
from nosolear.domain.errors import CapExceeded, ProviderUnavailable, RetryableProviderError


def flaky(n_failures: int, error: Exception):
    calls = []

    def call():
        calls.append(1)
        if len(calls) <= n_failures:
            raise error
        return "ok"

    return call, calls


def test_retries_after_1_2_4_8_then_gives_up():
    slept: list[float] = []
    call, calls = flaky(99, RetryableProviderError("Azure Speech is rate-limiting requests"))
    with pytest.raises(ProviderUnavailable) as info:
        retry_call(call, sleep=slept.append)
    assert not isinstance(info.value, RetryableProviderError)
    assert slept == [1, 2, 4, 8] and len(calls) == 5
    assert str(info.value) == "Azure Speech is rate-limiting requests"


def test_succeeds_after_two_retryable_errors():
    call, calls = flaky(2, RetryableProviderError("busy"))
    assert retry_call(call, sleep=lambda s: None) == "ok" and len(calls) == 3


@pytest.mark.parametrize("error", [ProviderUnavailable("bad key"), CapExceeded()])
def test_other_errors_are_not_retried(error):
    call, calls = flaky(1, error)
    with pytest.raises(type(error)):
        retry_call(call, sleep=lambda s: None)
    assert len(calls) == 1


def test_exhausted_retry_error_passes_the_leak_check():
    call, _ = flaky(99, RetryableProviderError("Azure Speech is rate-limiting requests"))
    with pytest.raises(ProviderUnavailable) as info:
        retry_call(call, sleep=lambda s: None)
    assert_no_leak(error=info.value)


def test_the_leak_check_has_teeth():
    with pytest.raises(AssertionError):
        assert_no_leak(texts=[f"the provider said {PROVIDER_BODY_MARKER}"])


def test_each_retrying_wrapper_retries_its_own_method(tmp_path):
    def busy(n: int) -> list[Exception]:
        return [RetryableProviderError("busy") for _ in range(n)]

    wav = tmp_path / "a.wav"
    scorer = FakeScorer(results=[assessment()], errors=busy(1))
    transcriber = FakeTranscriber(results=[transcript("hi")], errors=busy(1))
    tts = FakeSpeechSynthesizer(errors=busy(5))
    coach = FakeCoach(errors=busy(5))

    assert (
        RetryingPronunciationScorer(scorer, sleep=lambda s: None).score(wav, reference_text=None)
        == assessment()
    )
    assert RetryingTranscriber(transcriber, sleep=lambda s: None).transcribe(wav).text == "hi"
    assert len(scorer.calls) == 2 and len(transcriber.calls) == 2
    with pytest.raises(ProviderUnavailable):
        RetryingSpeechSynthesizer(tts, sleep=lambda s: None).synthesize("hi", rate_percent=0)
    assert len(tts.calls) == 5
    with pytest.raises(ProviderUnavailable):
        RetryingCoach(coach, sleep=lambda s: None).analyze(
            task=CoachTask.FREE_TALK, prompt_text="p", transcript="t", allowed_keys=[]
        )
    assert len(coach.calls) == 5
