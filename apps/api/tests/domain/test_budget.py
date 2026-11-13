from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nosolear.domain.budget import (
    DEFAULT_CAPS,
    Caps,
    Provider,
    Unit,
    ceil_seconds,
    fits,
    period_for,
)


def test_default_caps():
    assert DEFAULT_CAPS.azure_audio_seconds == 16200
    assert DEFAULT_CAPS.azure_tts_chars == 450000
    assert DEFAULT_CAPS.claude_tokens == 100000


def test_caps_convert_hours_to_seconds_floored():
    caps = Caps.from_hours_chars_tokens(
        azure_audio_hours=1.0001, azure_tts_chars=1, claude_tokens=1
    )
    assert caps.azure_audio_seconds == 3600
    assert (
        Caps.from_hours_chars_tokens(
            azure_audio_hours=0.5, azure_tts_chars=1, claude_tokens=1
        ).azure_audio_seconds
        == 1800
    )


def test_limit_returns_the_cap_for_each_supported_pair():
    assert DEFAULT_CAPS.limit(Provider.AZURE, Unit.AUDIO_SECONDS) == 16200
    assert DEFAULT_CAPS.limit(Provider.AZURE, Unit.TTS_CHARS) == 450000
    assert DEFAULT_CAPS.limit(Provider.ANTHROPIC, Unit.TOKENS) == 100000


def test_limit_rejects_unsupported_pair():
    with pytest.raises(ValueError):
        DEFAULT_CAPS.limit(Provider.ANTHROPIC, Unit.AUDIO_SECONDS)


def test_period_for_azure_is_the_utc_month():
    assert (
        period_for(
            Provider.AZURE, Unit.AUDIO_SECONDS, datetime(2026, 11, 30, 23, 59, 59, tzinfo=UTC)
        )
        == "2026-11"
    )
    assert (
        period_for(Provider.AZURE, Unit.TTS_CHARS, datetime(2026, 11, 30, 23, 59, 59, tzinfo=UTC))
        == "2026-11"
    )


def test_period_for_claude_is_the_utc_day():
    assert (
        period_for(Provider.ANTHROPIC, Unit.TOKENS, datetime(2026, 11, 30, 23, 59, 59, tzinfo=UTC))
        == "2026-11-30"
    )


def test_period_for_converts_to_utc_first():
    npt = timezone(timedelta(hours=5, minutes=45))
    moment = datetime(2026, 12, 1, 3, 0, tzinfo=npt)  # 2026-11-30T21:15Z
    assert period_for(Provider.AZURE, Unit.AUDIO_SECONDS, moment) == "2026-11"
    assert period_for(Provider.ANTHROPIC, Unit.TOKENS, moment) == "2026-11-30"


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        period_for(Provider.AZURE, Unit.AUDIO_SECONDS, datetime(2026, 11, 1))


def test_fits_boundary():
    assert fits(100, recorded=60, reserved=30, estimate=10) is True
    assert fits(100, recorded=60, reserved=30, estimate=11) is False


def test_ceil_seconds():
    assert ceil_seconds(0.0) == 0
    assert ceil_seconds(0.01) == 1
    assert ceil_seconds(3.0) == 3
    assert ceil_seconds(-4.2) == 0


@given(
    cap=st.integers(min_value=0, max_value=10_000),
    recorded=st.integers(min_value=0, max_value=10_000),
    reserved=st.integers(min_value=0, max_value=10_000),
    estimate=st.integers(min_value=0, max_value=10_000),
    smaller=st.integers(min_value=0, max_value=10_000),
)
def test_fits_is_monotone_in_estimate(cap, recorded, reserved, estimate, smaller):
    if fits(cap, recorded, reserved, estimate):
        assert fits(cap, recorded, reserved, min(smaller, estimate))
