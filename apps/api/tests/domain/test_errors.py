from nosolear.domain.errors import (
    CapabilityMissing,
    CapExceeded,
    InvalidAudio,
    NosolearError,
    ProviderUnavailable,
    RequestNotSent,
)


def test_default_messages_are_fixed_sentences():
    for cls in (CapExceeded, ProviderUnavailable, CapabilityMissing, RequestNotSent):
        err = cls()
        assert err.safe_message == cls.default_message
        assert str(err) == err.safe_message
        assert cls.default_message


def test_given_message_wins():
    err = ProviderUnavailable("Check NOSOLEAR_AZURE_SPEECH_KEY")
    assert err.safe_message == "Check NOSOLEAR_AZURE_SPEECH_KEY"
    assert str(err) == err.safe_message


def test_codes():
    assert CapExceeded.code == "cap_exceeded"
    assert ProviderUnavailable.code == "provider_unavailable"
    assert CapabilityMissing.code == "capability_missing"
    assert InvalidAudio.code == "invalid_audio"


def test_request_not_sent_is_provider_unavailable():
    err = RequestNotSent("Set the key")
    assert isinstance(err, ProviderUnavailable)
    assert RequestNotSent.code == "provider_unavailable"


def test_errors_are_value_errors():
    assert issubclass(NosolearError, ValueError)


def test_invalid_audio_carries_reason_and_safe_message():
    err = InvalidAudio("too_long")
    assert err.reason == "too_long"
    assert str(err) == err.safe_message
    assert err.safe_message
