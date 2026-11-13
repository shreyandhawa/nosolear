"""Reservation estimates, computed from the input before any call is made. Pure: no clock."""

import wave
from pathlib import Path

from nosolear.domain.budget import ceil_seconds
from nosolear.domain.errors import RequestNotSent


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
