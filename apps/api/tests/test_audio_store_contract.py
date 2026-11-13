import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest
from fakes import FakeAudioStore
from wavs import make_wav

from nosolear.adapters.filesystem_audio_store import FilesystemAudioStore
from nosolear.domain.audio import DEFAULT_LIMITS, AudioLimits, parse_wav
from nosolear.domain.errors import InvalidAudio
from nosolear.ports.audio import AudioStore

Factory = Callable[[AudioLimits], AudioStore]


@pytest.fixture(params=["filesystem", "fake"])
def make_store(request: pytest.FixtureRequest, tmp_path: Path) -> Factory:
    def build(limits: AudioLimits = DEFAULT_LIMITS) -> AudioStore:
        if request.param == "filesystem":
            return FilesystemAudioStore(tmp_path, limits=limits)
        return FakeAudioStore(limits)

    return build


def test_valid_commit_and_read(make_store: Factory) -> None:
    store = make_store(AudioLimits())
    pending = store.begin_upload()
    data = make_wav(1.0, rate=44100)
    pending.write(data[:5000])
    pending.write(data[5000:])
    stored = pending.commit()
    assert stored.path.startswith("recordings/") and stored.path.endswith(".wav")
    assert stored.sample_rate == 16000
    assert stored.duration_ms == 1000
    body = store.read(stored.path)
    assert parse_wav(body).sample_rate == 16000
    assert stored.sha256 == hashlib.sha256(body).hexdigest()


def test_over_cap_write(make_store: Factory) -> None:
    pending = make_store(AudioLimits(max_bytes=100)).begin_upload()
    with pytest.raises(InvalidAudio) as exc:
        pending.write(b"x" * 101)
    assert exc.value.reason == "too_large"
    with pytest.raises(RuntimeError):
        pending.commit()


def test_invalid_audio(make_store: Factory) -> None:
    pending = make_store(AudioLimits()).begin_upload()
    pending.write(b"not a wav at all")
    with pytest.raises(InvalidAudio) as exc:
        pending.commit()
    assert exc.value.reason == "not_wav"


def test_tiny_input_that_resamples_to_nothing(make_store: Factory) -> None:
    pending = make_store(AudioLimits()).begin_upload()
    pending.write(make_wav(1 / 22050, rate=22050))
    with pytest.raises(InvalidAudio) as exc:
        pending.commit()
    assert exc.value.reason == "empty"


def test_delete(make_store: Factory) -> None:
    store = make_store(AudioLimits())
    pending = store.begin_upload()
    pending.write(make_wav(0.2))
    stored = pending.commit()
    store.delete(stored.path)
    store.delete(stored.path)
    with pytest.raises((FileNotFoundError, KeyError)):
        store.read(stored.path)


def test_refuses_foreign_paths(make_store: Factory) -> None:
    store = make_store(AudioLimits())
    for bad in ("../x.wav", "/etc/passwd", "recordings/a.wav"):
        with pytest.raises(ValueError):
            store.resolve(bad)
