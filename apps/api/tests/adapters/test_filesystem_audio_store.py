import hashlib
import os
import re
import stat
import tempfile
from pathlib import Path

import pytest
from wavs import make_wav

from nosolear.adapters import filesystem_audio_store as fas
from nosolear.adapters.filesystem_audio_store import FilesystemAudioStore
from nosolear.domain.audio import AudioLimits, parse_wav
from nosolear.domain.errors import InvalidAudio

PATH_RE = re.compile(r"^recordings/[0-9a-f-]{36}\.wav$")


def upload(store: FilesystemAudioStore, data: bytes, chunk: int = 1000):
    pending = store.begin_upload()
    for i in range(0, len(data), chunk):
        pending.write(data[i : i + chunk])
    return pending


def test_commit_stores_16k_under_generated_name(tmp_path: Path) -> None:
    store = FilesystemAudioStore(tmp_path)
    stored = upload(store, make_wav(1.5, rate=48000)).commit()
    assert PATH_RE.match(stored.path)
    file = tmp_path / stored.path
    assert file.exists()
    audio = parse_wav(file.read_bytes())
    assert audio.sample_rate == 16000
    assert stored.sample_rate == 16000
    assert stored.duration_ms == 1500 == len(audio.samples) * 1000 // 16000
    assert stored.sha256 == hashlib.sha256(file.read_bytes()).hexdigest()


def test_permissions(tmp_path: Path) -> None:
    store = FilesystemAudioStore(tmp_path)
    stored = upload(store, make_wav(0.5)).commit()
    assert stat.S_IMODE((tmp_path / stored.path).stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "recordings").stat().st_mode) == 0o700


def test_temp_file_is_inside_data_dir_and_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom() -> str:
        raise AssertionError("system temp dir used")

    monkeypatch.setattr(tempfile, "gettempdir", boom)
    store = FilesystemAudioStore(tmp_path)
    incoming = tmp_path / "recordings" / ".incoming"

    pending = store.begin_upload()
    pending.write(b"abc")
    assert len(list(incoming.iterdir())) == 1
    pending.abort()
    assert list(incoming.iterdir()) == []

    pending = upload(store, make_wav(0.2))
    assert len(list(incoming.iterdir())) == 1
    pending.commit()
    assert list(incoming.iterdir()) == []


def test_write_past_cap_aborts(tmp_path: Path) -> None:
    store = FilesystemAudioStore(tmp_path, limits=AudioLimits(max_bytes=1000))
    pending = store.begin_upload()
    pending.write(b"x" * 600)
    with pytest.raises(InvalidAudio) as exc:
        pending.write(b"x" * 600)
    assert exc.value.reason == "too_large"
    assert list((tmp_path / "recordings" / ".incoming").iterdir()) == []


def test_commit_invalid_audio_leaves_nothing(tmp_path: Path) -> None:
    store = FilesystemAudioStore(tmp_path)
    pending = upload(store, b"garbage bytes that are not a wav file")
    with pytest.raises(InvalidAudio) as exc:
        pending.commit()
    assert exc.value.reason == "not_wav"
    assert [p.name for p in (tmp_path / "recordings").iterdir()] == [".incoming"]
    assert list((tmp_path / "recordings" / ".incoming").iterdir()) == []


def test_commit_empty_after_resample_stores_nothing(tmp_path: Path) -> None:
    store = FilesystemAudioStore(tmp_path)
    pending = upload(store, make_wav(1 / 22050, rate=22050))
    with pytest.raises(InvalidAudio) as exc:
        pending.commit()
    assert exc.value.reason == "empty"
    assert [p.name for p in (tmp_path / "recordings").iterdir()] == [".incoming"]
    assert list((tmp_path / "recordings" / ".incoming").iterdir()) == []


def test_failed_final_write_leaves_no_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FilesystemAudioStore(tmp_path)
    pending = upload(store, make_wav(0.5))
    real_write = os.write
    calls = {"n": 0}

    def flaky(fd: int, data: bytes | memoryview) -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            return real_write(fd, bytes(data)[:10])  # a partial write succeeds first
        raise OSError("disk full")

    monkeypatch.setattr(fas.os, "write", flaky)
    with pytest.raises(OSError):
        pending.commit()
    monkeypatch.undo()
    assert [p.name for p in (tmp_path / "recordings").iterdir()] == [".incoming"]
    assert list((tmp_path / "recordings" / ".incoming").iterdir()) == []


def test_unexpected_error_in_commit_removes_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FilesystemAudioStore(tmp_path)
    pending = upload(store, make_wav(0.5))

    def boom(*_args: object, **_kw: object) -> None:
        raise MemoryError

    monkeypatch.setattr(fas, "to_16k", boom)
    with pytest.raises(MemoryError):
        pending.commit()
    assert list((tmp_path / "recordings" / ".incoming").iterdir()) == []


def test_abort_is_idempotent_and_write_after_finish_raises(tmp_path: Path) -> None:
    store = FilesystemAudioStore(tmp_path)
    pending = store.begin_upload()
    pending.write(b"abc")
    pending.abort()
    pending.abort()
    with pytest.raises(RuntimeError):
        pending.write(b"more")
    with pytest.raises(RuntimeError):
        pending.commit()

    done = upload(store, make_wav(0.2))
    done.commit()
    with pytest.raises(RuntimeError):
        done.write(b"more")
    with pytest.raises(RuntimeError):
        done.commit()
    done.abort()
    assert list((tmp_path / "recordings" / ".incoming").iterdir()) == []
    assert len([p for p in (tmp_path / "recordings").iterdir() if p.name != ".incoming"]) == 1


def test_two_commits_get_distinct_names(tmp_path: Path) -> None:
    store = FilesystemAudioStore(tmp_path)
    a = upload(store, make_wav(0.2)).commit()
    b = upload(store, make_wav(0.2)).commit()
    assert a.path != b.path


@pytest.mark.parametrize(
    "bad",
    [
        "../x.wav",
        "/etc/passwd",
        "recordings/../../x.wav",
        "recordings/a.wav",
        "recordings/" + "0" * 36 + ".mp3",
        "recordings/.incoming/x",
        "link",
    ],
)
def test_resolve_refuses_paths_outside_recordings(tmp_path: Path, bad: str) -> None:
    data = tmp_path / "data"
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"secret")
    store = FilesystemAudioStore(data)
    link_name = "0" * 36 + ".wav"
    (data / "recordings" / link_name).symlink_to(outside)
    path = f"recordings/{link_name}" if bad == "link" else bad
    with pytest.raises(ValueError):
        store.resolve(path)
    with pytest.raises(ValueError):
        store.read(path)
    with pytest.raises(ValueError):
        store.delete(path)
    assert outside.read_bytes() == b"secret"


def test_resolve_returns_absolute_path_of_stored_file(tmp_path: Path) -> None:
    store = FilesystemAudioStore(tmp_path)
    stored = upload(store, make_wav(0.2)).commit()
    assert store.resolve(stored.path) == (tmp_path / stored.path).resolve()


def test_startup_sweeps_stale_incoming_files(tmp_path: Path) -> None:
    FilesystemAudioStore(tmp_path)
    stale = tmp_path / "recordings" / ".incoming" / "x.part"
    stale.write_bytes(b"left over")
    FilesystemAudioStore(tmp_path)
    assert not stale.exists()


def test_delete_removes_file_and_is_idempotent(tmp_path: Path) -> None:
    store = FilesystemAudioStore(tmp_path)
    stored = upload(store, make_wav(0.2)).commit()
    store.delete(stored.path)
    assert not (tmp_path / stored.path).exists()
    store.delete(stored.path)
