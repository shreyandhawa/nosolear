"""Shared helpers for the Phase 0b spikes: paths, Azure config, budget log, backoff, resampler."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from math import gcd
from pathlib import Path
from typing import Callable, TypeVar

import numpy as np
import soundfile as sf
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data" / "spikes"
USAGE_LOG = DATA / "usage.jsonl"
SKIPPED_LOG = DATA / "skipped.jsonl"
BUDGET_SECONDS = 900
TARGET_RATE = 16000

T = TypeVar("T")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def speech_config():
    """SpeechConfig from the repo-root .env. The key is never printed or logged."""
    import azure.cognitiveservices.speech as speechsdk

    load_dotenv(REPO / ".env")
    key = os.environ.get("NOSOLEAR_AZURE_SPEECH_KEY")
    region = os.environ.get("NOSOLEAR_AZURE_SPEECH_REGION")
    if not key or not region:
        raise RuntimeError("NOSOLEAR_AZURE_SPEECH_KEY / _REGION missing from .env")
    return speechsdk.SpeechConfig(subscription=key, region=region)


def _rows() -> list[dict]:
    if not USAGE_LOG.exists():
        return []
    return [json.loads(line) for line in USAGE_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]


def usage_total() -> float:
    """Total recognition seconds used so far (TTS rows are excluded)."""
    return float(sum(r.get("seconds", 0) for r in _rows() if r.get("provider") != "azure_tts"))


def log_usage(provider: str, seconds: float, *, chars: int | None = None) -> None:
    """Append a usage row. Call BEFORE each Azure call. Raises, writing nothing, if over budget."""
    if provider != "azure_tts" and usage_total() + seconds > BUDGET_SECONDS:
        raise RuntimeError("Azure spike budget exceeded")
    row: dict = {"ts": _now(), "provider": provider, "seconds": seconds}
    if chars is not None:
        row["chars"] = chars
    _append(USAGE_LOG, row)


def _is_429(result) -> bool:
    import azure.cognitiveservices.speech as speechsdk

    if result.reason != speechsdk.ResultReason.Canceled:
        return False
    try:
        details = result.cancellation_details
    except AttributeError:
        details = speechsdk.SpeechSynthesisCancellationDetails(result)
    if details.reason != speechsdk.CancellationReason.Error:
        return False
    text = details.error_details or ""
    return details.error_code == speechsdk.CancellationErrorCode.TooManyRequests or "429" in text


def with_backoff(fn: Callable[[], T], label: str = "azure call") -> T | None:
    """Run fn(); on Azure 429 retry after 1, 2, 4, 8 s, then give up (None) and log the skip."""
    result = fn()
    for delay in (1, 2, 4, 8):
        if not _is_429(result):
            return result
        time.sleep(delay)
        result = fn()
    if not _is_429(result):
        return result
    print(f"SKIPPED (429 after retries): {label}", file=sys.stderr)
    _append(SKIPPED_LOG, {"ts": _now(), "label": label, "reason": "429 after 4 retries"})
    return None


# ---- resampling (numpy only; soundfile cannot resample) ----

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


def resample_to_16k(x: np.ndarray, rate: int) -> np.ndarray:
    """Mono float -> 16 kHz: anti-alias low-pass (7.6 kHz) then decimate (integer ratio) or interpolate."""
    x = np.asarray(x, dtype=np.float64)
    if rate == TARGET_RATE:
        return x
    if rate > TARGET_RATE:
        x = _fft_filter(x, _lowpass_kernel(7600, rate))
    if rate % TARGET_RATE == 0:
        return x[:: rate // TARGET_RATE]
    n_out = int(len(x) * TARGET_RATE / rate)
    t = np.arange(n_out) * rate / TARGET_RATE
    return np.interp(t, np.arange(len(x)), x)


def write_wav16k(path: Path, x: np.ndarray, rate: int) -> None:
    """Resample mono audio to 16 kHz and write it as 16-bit PCM WAV."""
    y = np.clip(resample_to_16k(x, rate), -1.0, 1.0)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), y, TARGET_RATE, subtype="PCM_16")
