"""The shared Azure client, tested through the fake backend. No SDK import and no network."""

import logging
import threading

import pytest
from provider_fakes import FakeSpeechBackend
from pydantic import SecretStr
from security.planted import PLANTED_AZURE_KEY, PROVIDER_BODY_MARKER, assert_no_leak

from nosolear.adapters.azure_speech import AzureSpeech, Cancellation, classify
from nosolear.domain.errors import (
    ProviderUnavailable,
    RequestNotSent,
    RetryableProviderError,
)

NOT_CONFIGURED = (
    "Azure Speech isn't configured: set NOSOLEAR_AZURE_SPEECH_KEY and "
    "NOSOLEAR_AZURE_SPEECH_REGION in .env"
)


def configured(backend: FakeSpeechBackend, region: str = "eastus") -> AzureSpeech:
    return AzureSpeech(key=SecretStr(PLANTED_AZURE_KEY), region=region, backend=backend)


def test_not_configured_is_request_not_sent_and_backend_untouched():
    backend = FakeSpeechBackend()
    with pytest.raises(RequestNotSent) as info:
        AzureSpeech(key=None, region="eastus", backend=backend).synthesize("<speak/>")
    assert str(info.value) == NOT_CONFIGURED
    assert backend.calls == []


def test_missing_region_is_request_not_sent():
    backend = FakeSpeechBackend()
    with pytest.raises(RequestNotSent):
        AzureSpeech(key=SecretStr(PLANTED_AZURE_KEY), region=None, backend=backend).synthesize(
            "<speak/>"
        )
    assert backend.calls == []


@pytest.mark.parametrize("region", ["east us", "evil.example.com/x", "EastUS"])
def test_region_must_be_lowercase_alnum(region):
    with pytest.raises(ValueError):
        AzureSpeech(key=SecretStr(PLANTED_AZURE_KEY), region=region, backend=FakeSpeechBackend())


def test_one_azure_request_at_a_time():
    backend = FakeSpeechBackend(delay_s=0.05)  # tracks the most calls in flight at once
    speech = configured(backend)
    threads = [threading.Thread(target=speech.synthesize, args=("<speak/>",)) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(backend.calls) == 4
    assert backend.max_concurrent == 1


def test_cancellation_details_never_leak(caplog):
    caplog.set_level(logging.DEBUG)
    backend = FakeSpeechBackend(
        cancel=Cancellation(
            "AuthenticationFailure", f"bad {PLANTED_AZURE_KEY} {PROVIDER_BODY_MARKER}"
        )
    )
    with pytest.raises(ProviderUnavailable) as info:
        configured(backend).synthesize("<speak/>")
    assert "NOSOLEAR_AZURE_SPEECH_KEY" in str(info.value)
    assert_no_leak(error=info.value, logs=caplog.text)


@pytest.mark.parametrize(
    ("code", "details", "retryable", "message"),
    [
        ("TooManyRequests", "", True, "Azure Speech is rate-limiting requests"),
        ("ServiceError", "HTTP 429 from upstream", True, "Azure Speech is rate-limiting requests"),
        ("ServiceError", "", True, "Azure Speech is unavailable"),
        ("ServiceTimeout", "", True, "Azure Speech is unavailable"),
        ("ConnectionFailure", "", True, "Azure Speech is unavailable"),
        ("ServiceUnavailable", "", True, "Azure Speech is unavailable"),
        (
            "AuthenticationFailure",
            "",
            False,
            "Azure Speech rejected the key or region; check NOSOLEAR_AZURE_SPEECH_KEY and "
            "NOSOLEAR_AZURE_SPEECH_REGION",
        ),
        (
            "Forbidden",
            "",
            False,
            "Azure Speech rejected the key or region; check NOSOLEAR_AZURE_SPEECH_KEY and "
            "NOSOLEAR_AZURE_SPEECH_REGION",
        ),
        ("BadRequest", "", False, "Azure Speech rejected the request"),
        ("RuntimeError", "", False, "Azure Speech failed"),
    ],
)
def test_classify(code, details, retryable, message):
    error = classify(Cancellation(code, details))
    assert isinstance(error, RetryableProviderError) is retryable
    assert str(error) == message
