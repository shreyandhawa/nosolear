"""Synthetic WAV builders. All audio is generated in memory; no real voice, no files."""

from __future__ import annotations

import struct

import numpy as np


def raw_wav(
    *,
    rate: int,
    pcm: bytes,
    declared_data: int | None = None,
    riff_size: int | None = None,
    extra_chunks: bytes = b"",
    fmt_tag: int = 1,
    channels: int = 1,
    bits: int = 16,
) -> bytes:
    """Build a WAV with a hand-made header so tests can lie about sizes or formats.

    `extra_chunks` is placed between the `fmt ` and `data` chunks.
    """
    block_align = channels * bits // 8
    fmt = struct.pack("<HHIIHH", fmt_tag, channels, rate, rate * block_align, block_align, bits)
    data_size = len(pcm) if declared_data is None else declared_data
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
    body += extra_chunks + b"data" + struct.pack("<I", data_size) + pcm
    size = len(body) if riff_size is None else riff_size
    return b"RIFF" + struct.pack("<I", size) + body


def make_wav(seconds: float, rate: int = 16000, freq: float | None = 440.0) -> bytes:
    """A mono 16-bit WAV: a sine at `freq` Hz, or silence when `freq` is None."""
    n = round(seconds * rate)
    if freq is None:
        samples = np.zeros(n, dtype="<i2")
    else:
        t = np.arange(n) / rate
        samples = np.round(0.5 * 32767 * np.sin(2 * np.pi * freq * t)).astype("<i2")
    return raw_wav(rate=rate, pcm=samples.tobytes())
