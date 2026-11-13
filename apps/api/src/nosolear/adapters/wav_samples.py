"""Read the canonical 16 kHz mono 16-bit WAV as a float32 array.

Local engines take the array directly, so none of them shells out to ffmpeg or decodes with PyAV.
"""

import wave
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

SAMPLE_RATE = 16000


def read_16k_mono(wav: Path) -> NDArray[np.float32]:
    with wave.open(str(wav), "rb") as reader:
        if (
            reader.getnchannels() != 1
            or reader.getsampwidth() != 2
            or reader.getframerate() != SAMPLE_RATE
        ):
            raise ValueError("expected a 16 kHz mono 16-bit WAV")
        frames = reader.readframes(reader.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
