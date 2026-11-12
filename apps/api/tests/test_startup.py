import io
import logging
import os
import stat
from pathlib import Path

import pytest
from factories import make_settings

from nosolear.startup import prepare_process

KEY = "sk-test-0123456789abcdef"


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_does_not_create_dir_when_told_not_to(tmp_path: Path) -> None:
    data = tmp_path / "missing"
    prepare_process(make_settings(data_dir=data), create_data_dir=False)
    assert not data.exists()


def test_tightens_phase_0a_layout(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    data.chmod(0o755)
    names = ["nosolear.sqlite", "nosolear.sqlite-wal", "nosolear.sqlite-shm"]
    for name in names:
        (data / name).write_text("x")
        (data / name).chmod(0o644)
    prepare_process(make_settings(data_dir=data), create_data_dir=True)
    assert mode(data) == 0o700
    assert all(mode(data / n) == 0o600 for n in names)


def test_telemetry_disabled(tmp_path: Path) -> None:
    prepare_process(make_settings(data_dir=tmp_path / "d"), create_data_dir=False)
    assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"


def test_preset_telemetry_value_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_HUB_DISABLE_TELEMETRY", "0")
    prepare_process(make_settings(data_dir=tmp_path / "d"), create_data_dir=False)
    assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "0"


def test_installs_scrubbing(tmp_path: Path) -> None:
    other = "azure-key-0123456789abcdef"
    prepare_process(
        make_settings(data_dir=tmp_path / "d", anthropic_api_key=KEY, azure_speech_key=other),
        create_data_dir=False,
    )
    stream = io.StringIO()
    log = logging.getLogger("t.startup")
    log.handlers = [logging.StreamHandler(stream)]
    log.propagate = False
    log.warning("k=%s and %s", KEY, other)
    assert KEY not in stream.getvalue()
    assert other not in stream.getvalue()
    assert stream.getvalue().count("[redacted]") == 2


def test_umask_is_owner_only_when_creating(tmp_path: Path) -> None:
    prepare_process(make_settings(data_dir=tmp_path / "d"), create_data_dir=True)
    probe = tmp_path / "d" / "probe"
    probe.write_text("x")
    assert mode(probe) == 0o600
