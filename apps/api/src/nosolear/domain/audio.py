"""Pure WAV parsing, validation and resampling. No I/O."""

from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

from nosolear.domain.errors import InvalidAudio

TARGET_RATE = 16_000
ALLOWED_SAMPLE_RATES: frozenset[int] = frozenset({16000, 22050, 24000, 32000, 44100, 48000})


@dataclass(frozen=True, slots=True)
class AudioLimits:
    max_bytes: int = 10 * 1024 * 1024
    max_duration_s: int = 120


DEFAULT_LIMITS = AudioLimits()


@dataclass(frozen=True, slots=True)
class WavAudio:
    """Mono 16-bit samples (int16, 1-D) at `sample_rate`."""

    sample_rate: int
    samples: np.ndarray


def check_declared_length(content_length: str | None, limits: AudioLimits = DEFAULT_LIMITS) -> None:
    """Refuse an upload whose Content-Length is malformed or over the byte cap."""
    if content_length is None:
        return
    try:
        value = int(content_length)
    except ValueError:
        raise InvalidAudio("not_wav") from None
    if value < 0:
        raise InvalidAudio("not_wav")
    if value > limits.max_bytes:
        raise InvalidAudio("too_large")


def parse_wav(data: bytes, limits: AudioLimits = DEFAULT_LIMITS) -> WavAudio:
    """Parse and validate a 16-bit PCM mono WAV.

    The RIFF size and the declared data size are untrusted: the frames actually received decide
    the duration.
    """
    if len(data) > limits.max_bytes:
        raise InvalidAudio("too_large")
    if len(data) < 12 or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise InvalidAudio("not_wav")

    rate: int | None = None
    payload: bytes | None = None
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        (declared,) = struct.unpack_from("<I", data, pos + 4)
        start = pos + 8
        size = min(declared, len(data) - start)
        if chunk_id == b"fmt ":
            if rate is not None or size < 16 or declared < 16:
                raise InvalidAudio("bad_chunks")
            tag, channels, rate, _byte_rate, _align, bits = struct.unpack_from(
                "<HHIIHH", data, start
            )
            if tag != 1 or channels != 1 or bits != 16:
                raise InvalidAudio("unsupported_format")
            if rate not in ALLOWED_SAMPLE_RATES:
                raise InvalidAudio("bad_sample_rate")
        elif chunk_id == b"data":
            if payload is not None:
                raise InvalidAudio("bad_chunks")
            payload = data[start : start + size]
        pos = start + declared + (declared & 1)

    if rate is None or payload is None:
        raise InvalidAudio("bad_chunks")
    frames = len(payload) // 2
    if frames == 0:
        raise InvalidAudio("empty")
    if frames > limits.max_duration_s * rate:
        raise InvalidAudio("too_long")
    samples = np.frombuffer(payload[: frames * 2], dtype="<i2").astype(np.int16)
    return WavAudio(sample_rate=rate, samples=samples)


def _lowpass_kernel(cutoff_hz: float, rate: int, taps: int = 1023) -> np.ndarray:
    n = np.arange(taps) - (taps - 1) / 2
    fc = cutoff_hz / rate
    h = 2 * fc * np.sinc(2 * fc * n) * np.blackman(taps)
    return h / h.sum()


def _fft_filter(x: np.ndarray, h: np.ndarray) -> np.ndarray:
    """Zero-phase FIR filter (same length) by FFT convolution."""
    n = len(x) + len(h) - 1
    size = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(h, size), size)[:n]
    d = (len(h) - 1) // 2
    return y[d : d + len(x)]


def resample_to_16k(samples: np.ndarray, rate: int) -> np.ndarray:
    """Mono float to 16 kHz: anti-alias low-pass (7.6 kHz), then decimate or interpolate."""
    if rate not in ALLOWED_SAMPLE_RATES:
        raise InvalidAudio("bad_sample_rate")
    x = np.asarray(samples, dtype=np.float64)
    if len(x) == 0 or rate == TARGET_RATE:
        return x
    x = _fft_filter(x, _lowpass_kernel(7600, rate))
    if rate % TARGET_RATE == 0:
        return x[:: rate // TARGET_RATE]
    n_out = int(len(x) * TARGET_RATE / rate)
    t = np.arange(n_out) * rate / TARGET_RATE
    return np.interp(t, np.arange(len(x)), x)


def to_16k(audio: WavAudio) -> np.ndarray:
    """int16 audio at any allowed rate to int16 at 16 kHz."""
    x = audio.samples.astype(np.float64) / 32768.0
    y = np.clip(resample_to_16k(x, audio.sample_rate), -1.0, 32767 / 32768)
    return np.round(y * 32768.0).astype(np.int16)


def encode_wav(samples: np.ndarray, rate: int = TARGET_RATE) -> bytes:
    """Canonical 44-byte header followed by 16-bit PCM mono data."""
    pcm = np.clip(np.round(np.asarray(samples, dtype=np.float64)), -32768, 32767)
    body = pcm.astype("<i2").tobytes()
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    header = b"RIFF" + struct.pack("<I", 36 + len(body)) + b"WAVE"
    header += b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(body))
    return header + body


def duration_ms(frames: int, rate: int) -> int:
    return frames * 1000 // rate
