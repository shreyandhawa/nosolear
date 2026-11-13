from pathlib import Path

import pytest
from wavs import write_wav

from nosolear.budget.estimators import audio_seconds
from nosolear.domain.errors import RequestNotSent


def test_a_2_4_second_wav_estimates_3_seconds(tmp_path):
    assert audio_seconds(write_wav(tmp_path / "a.wav", 2.4)) == 3


def test_a_whole_second_wav_is_not_rounded_up(tmp_path):
    assert audio_seconds(write_wav(tmp_path / "a.wav", 2.0)) == 2


@pytest.mark.parametrize("content", [b"", b"not a wav at all", b"RIFF\x00\x00"])
def test_a_non_wav_file_is_refused_before_any_reservation(tmp_path, content: bytes):
    path: Path = tmp_path / "bad.wav"
    path.write_bytes(content)
    with pytest.raises(RequestNotSent):
        audio_seconds(path)
