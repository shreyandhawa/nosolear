"""Reservation estimates, computed from the input before any call is made. Pure: no clock."""

import json
import wave
from pathlib import Path

from nosolear.domain.budget import ceil_seconds
from nosolear.domain.coach import CoachRequest
from nosolear.domain.errors import RequestNotSent
from nosolear.domain.ssml import FALLBACK_VOICE, build_ssml

CLAUDE_OVERHEAD_TOKENS = 1000
"""Allowance for the request beyond its text and schema (ARCHITECTURE.md section 11)."""


def audio_seconds(wav: Path) -> int:
    """The WAV's duration rounded up to whole seconds. A file that is not a readable WAV raises
    `RequestNotSent`, so no reservation is made for input the provider would never bill."""
    try:
        with wave.open(str(wav), "rb") as reader:
            rate = reader.getframerate()
            if rate <= 0:
                raise RequestNotSent("The recording is not a readable WAV file.")
            return ceil_seconds(reader.getnframes() / rate)
    except wave.Error, EOFError:
        raise RequestNotSent("The recording is not a readable WAV file.") from None


def tts_chars(text: str, *, voice: str, locale: str, rate_percent: int) -> int:
    """The characters a synthesis may bill: the SSML for the configured voice, plus the SSML for
    the fallback voice when the two differ, since a rejection retries once with the fallback."""
    total = len(build_ssml(text, voice=voice, locale=locale, rate_percent=rate_percent))
    if voice != FALLBACK_VOICE:
        total += len(
            build_ssml(text, voice=FALLBACK_VOICE, locale=locale, rate_percent=rate_percent)
        )
    return total


def claude_tokens(request: CoachRequest) -> int:
    """An upper bound for a coach call: the request's UTF-8 bytes, a fixed allowance, and the
    largest reply the request allows."""
    text = request.system + request.user + json.dumps(dict(request.schema), sort_keys=True)
    return len(text.encode()) + CLAUDE_OVERHEAD_TOKENS + request.max_tokens
