"""Which transcriber runs: an explicit setting, or `auto` over the candidates that are installed
and fast enough (ARCHITECTURE.md section 18). Pure: the caller measures speed and checks installs.

An explicit choice is always honoured, with a warning when it is not installed or was measured
slower than `MAX_REAL_TIME_FACTOR`. `auto` skips a candidate that is not installed or measured too
slow, keeps one that was never measured, and always ends at `azure_stt`. `crisper_whisper` is never
chosen by `auto`.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class TranscriberName(StrEnum):
    MLX_WHISPER = "mlx_whisper"
    FASTER_WHISPER = "faster_whisper"
    AZURE_STT = "azure_stt"
    CRISPER_WHISPER = "crisper_whisper"


class Platform(StrEnum):
    MACOS_ARM64 = "macos_arm64"
    LINUX = "linux"
    OTHER = "other"


MAX_REAL_TIME_FACTOR = 1 / 3

_APPLE_CANDIDATES = (
    TranscriberName.MLX_WHISPER,
    TranscriberName.FASTER_WHISPER,
    TranscriberName.AZURE_STT,
)
_OTHER_CANDIDATES = (TranscriberName.FASTER_WHISPER, TranscriberName.AZURE_STT)
_INSTALL_HINT = {
    TranscriberName.MLX_WHISPER: "not installed: run `uv sync --extra apple`",
    TranscriberName.FASTER_WHISPER: "not installed: run `uv sync --extra local`",
    TranscriberName.CRISPER_WHISPER: "not installed: run `uv sync --extra local`",
    TranscriberName.AZURE_STT: "not installed",
}


@dataclass(frozen=True, slots=True)
class TranscriberChoice:
    name: TranscriberName
    auto: bool
    skipped: tuple[tuple[TranscriberName, str], ...]
    warning: str | None


def _factor(value: float) -> str:
    return f"{round(value, 2):g}"


def _explicit(
    name: TranscriberName,
    installed: frozenset[TranscriberName],
    real_time_factors: Mapping[TranscriberName, float],
) -> TranscriberChoice:
    notes: list[str] = []
    if name not in installed:
        notes.append(_INSTALL_HINT[name])
    factor = real_time_factors.get(name)
    if factor is not None and factor > MAX_REAL_TIME_FACTOR:
        notes.append(f"slower than 1/3 real time ({_factor(factor)}\u00d7)")
    return TranscriberChoice(
        name=name,
        auto=False,
        skipped=(),
        warning="; ".join(notes) if notes else None,
    )


def _auto(
    platform: Platform,
    installed: frozenset[TranscriberName],
    real_time_factors: Mapping[TranscriberName, float],
) -> TranscriberChoice:
    candidates = _APPLE_CANDIDATES if platform is Platform.MACOS_ARM64 else _OTHER_CANDIDATES
    skipped: list[tuple[TranscriberName, str]] = []
    for name in candidates:
        if name is TranscriberName.AZURE_STT:
            return TranscriberChoice(name, auto=True, skipped=tuple(skipped), warning=None)
        if name not in installed:
            skipped.append((name, "not installed"))
            continue
        factor = real_time_factors.get(name)
        if factor is not None and factor > MAX_REAL_TIME_FACTOR:
            skipped.append((name, f"too slow: {_factor(factor)}\u00d7 real time"))
            continue
        return TranscriberChoice(name, auto=True, skipped=tuple(skipped), warning=None)
    raise AssertionError("azure_stt is always a candidate and is always chosen")


def choose_transcriber(
    setting: str,
    *,
    platform: Platform,
    installed: frozenset[TranscriberName],
    real_time_factors: Mapping[TranscriberName, float],
) -> TranscriberChoice:
    if setting == "auto":
        return _auto(platform, installed, real_time_factors)
    return _explicit(TranscriberName(setting), installed, real_time_factors)
