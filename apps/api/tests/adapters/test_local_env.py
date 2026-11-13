import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from nosolear.adapters import local_env
from nosolear.adapters.local_env import (
    current_platform,
    espeak_ng_path,
    installed_transcribers,
    phone_probe_installed,
    select_device,
    torch_device,
)
from nosolear.domain.transcriber_choice import Platform, TranscriberName


def test_select_device_prefers_mps_then_cuda_then_cpu():
    assert select_device(mps=True, cuda=True) == "mps"
    assert select_device(mps=False, cuda=True) == "cuda"
    assert select_device(mps=False, cuda=False) == "cpu"


def test_torch_device_reads_the_backend_flags(monkeypatch):
    def flag(value):
        return SimpleNamespace(is_available=lambda: value)

    fake = SimpleNamespace(backends=SimpleNamespace(mps=flag(False)), cuda=flag(True))
    monkeypatch.setitem(sys.modules, "torch", fake)
    assert torch_device() == "cuda"


def test_installed_transcribers_always_contains_azure(monkeypatch):
    monkeypatch.setattr(local_env, "_installed", lambda name: False)
    assert installed_transcribers() == frozenset({TranscriberName.AZURE_STT})


def test_installed_transcribers_follow_the_installed_libraries(monkeypatch):
    present = {"faster_whisper", "transformers", "torch"}
    monkeypatch.setattr(local_env, "_installed", lambda name: name in present)
    assert installed_transcribers() == frozenset(
        {TranscriberName.AZURE_STT, TranscriberName.FASTER_WHISPER, TranscriberName.CRISPER_WHISPER}
    )


def test_phone_probe_needs_both_transformers_and_torch(monkeypatch):
    monkeypatch.setattr(local_env, "_installed", lambda name: name == "torch")
    assert phone_probe_installed() is False
    monkeypatch.setattr(local_env, "_installed", lambda name: True)
    assert phone_probe_installed() is True


def test_current_platform_maps_apple_silicon(monkeypatch):
    monkeypatch.setattr(local_env, "_system", lambda: ("darwin", "arm64"))
    assert current_platform() is Platform.MACOS_ARM64
    monkeypatch.setattr(local_env, "_system", lambda: ("darwin", "x86_64"))
    assert current_platform() is Platform.OTHER
    monkeypatch.setattr(local_env, "_system", lambda: ("linux", "x86_64"))
    assert current_platform() is Platform.LINUX


@pytest.mark.parametrize("found", [None, "/opt/tools/espeak-ng"])
def test_espeak_ng_path_is_found_on_the_path(monkeypatch, found):
    monkeypatch.setattr(local_env.shutil, "which", lambda name: found)
    expected = None if found is None else Path(found)
    assert espeak_ng_path() == expected
