from pathlib import Path

import pytest
from wavs import write_wav

from nosolear.budget.estimators import audio_seconds, tts_chars
from nosolear.domain.errors import RequestNotSent
from nosolear.domain.ssml import FALLBACK_VOICE, build_ssml


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


def test_tts_chars_is_the_ssml_length_of_the_voice_alone_when_it_is_the_fallback():
    estimate = tts_chars("hello", voice=FALLBACK_VOICE, locale="en-US", rate_percent=0)
    assert estimate == len(build_ssml("hello", voice=FALLBACK_VOICE, locale="en-US"))


def test_tts_chars_adds_the_fallback_when_the_voice_differs():
    estimate = tts_chars("hello", voice="en-US-JennyNeural", locale="en-US", rate_percent=-25)
    expected = len(
        build_ssml("hello", voice="en-US-JennyNeural", locale="en-US", rate_percent=-25)
    ) + len(build_ssml("hello", voice=FALLBACK_VOICE, locale="en-US", rate_percent=-25))
    assert estimate == expected
