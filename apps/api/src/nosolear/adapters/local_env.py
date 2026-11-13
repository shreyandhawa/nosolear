"""What this machine can run locally: platform, installed libraries, espeak-ng and devices.

Nothing here imports a heavy library. Installs are checked with `importlib.util.find_spec`, and
torch is imported only when a device is asked for, so the base install never loads it.
"""

import importlib.metadata
import importlib.util
import platform
import shutil
import sys
from pathlib import Path
from typing import Literal, Protocol, cast

from nosolear.domain.transcriber_choice import Platform, TranscriberName

Device = Literal["mps", "cuda", "cpu"]


class _Flag(Protocol):
    def is_available(self) -> bool: ...


class _Backends(Protocol):
    mps: _Flag


class _Torch(Protocol):
    backends: _Backends
    cuda: _Flag


def _system() -> tuple[str, str]:
    return sys.platform, platform.machine()


def _installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def installed_version(distribution: str) -> str:
    """The installed version of a distribution, read from its metadata (nothing is imported)."""
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def current_platform() -> Platform:
    system, machine = _system()
    if system == "darwin" and machine.lower() in {"arm64", "aarch64"}:
        return Platform.MACOS_ARM64
    if system.startswith("linux"):
        return Platform.LINUX
    return Platform.OTHER


def phone_probe_installed() -> bool:
    return _installed("transformers") and _installed("torch")


def installed_transcribers() -> frozenset[TranscriberName]:
    found = {TranscriberName.AZURE_STT}
    if _installed("faster_whisper"):
        found.add(TranscriberName.FASTER_WHISPER)
    if _installed("mlx_whisper"):
        found.add(TranscriberName.MLX_WHISPER)
    if phone_probe_installed():
        found.add(TranscriberName.CRISPER_WHISPER)
    return frozenset(found)


def espeak_ng_path() -> Path | None:
    found = shutil.which("espeak-ng")
    return None if found is None else Path(found)


def select_device(*, mps: bool, cuda: bool) -> Device:
    if mps:
        return "mps"
    if cuda:
        return "cuda"
    return "cpu"


def torch_device() -> str:
    import torch  # pyright: ignore[reportMissingImports]

    module = cast("_Torch", torch)
    return select_device(mps=module.backends.mps.is_available(), cuda=module.cuda.is_available())
