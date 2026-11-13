import numpy as np
import pytest
from wavs import make_wav, raw_wav

from nosolear.domain.audio import (
    ALLOWED_SAMPLE_RATES,
    check_declared_length,
    duration_ms,
    encode_wav,
    parse_wav,
    resample_to_16k,
)
from nosolear.domain.errors import InvalidAudio


def pcm(seconds: float, rate: int) -> bytes:
    return np.zeros(round(seconds * rate), dtype="<i2").tobytes()


def reason_of(data: bytes) -> str:
    with pytest.raises(InvalidAudio) as exc:
        parse_wav(data)
    return exc.value.reason


def test_parses_valid_wav():
    audio = parse_wav(make_wav(1.0))
    assert audio.sample_rate == 16000
    assert len(audio.samples) == 16000
    assert audio.samples.dtype == np.int16


def test_duration_uses_frames_received():
    rate = 16000
    for declared in (100 * rate * 2, 0xFFFFFFFF):
        audio = parse_wav(raw_wav(rate=rate, pcm=pcm(2, rate), declared_data=declared))
        assert len(audio.samples) == 2 * rate


def test_declared_smaller_than_file_ignores_trailing_junk_chunk():
    rate = 16000
    body = pcm(1, rate)
    junk = b"LIST" + (4).to_bytes(4, "little") + b"abcd"
    data = raw_wav(rate=rate, pcm=body + junk, declared_data=len(body))
    assert len(parse_wav(data).samples) == rate
    assert len(parse_wav(data + b"xyz").samples) == rate


def test_rejects_second_data_chunk_and_second_fmt_chunk():
    rate = 16000
    base = raw_wav(rate=rate, pcm=pcm(1, rate))
    second_data = base + b"data" + (2).to_bytes(4, "little") + b"\x00\x00"
    assert reason_of(second_data) == "bad_chunks"
    fmt_chunk = base[12:36]
    two_fmt = raw_wav(rate=rate, pcm=pcm(1, rate), extra_chunks=fmt_chunk)
    assert reason_of(two_fmt) == "bad_chunks"


def test_rejects_missing_fmt_or_data():
    only_fmt = raw_wav(rate=16000, pcm=b"")[:36]
    assert reason_of(only_fmt) == "bad_chunks"
    no_fmt = b"RIFF" + (12).to_bytes(4, "little") + b"WAVE" + b"data" + (2).to_bytes(4, "little")
    assert reason_of(no_fmt + b"\x00\x00") == "bad_chunks"


@pytest.mark.parametrize(
    "kwargs",
    [{"fmt_tag": 3}, {"fmt_tag": 0xFFFE}, {"bits": 8}, {"bits": 24}, {"channels": 2}],
)
def test_rejects_non_pcm16_mono(kwargs):
    data = raw_wav(rate=16000, pcm=pcm(1, 16000), **kwargs)
    assert reason_of(data) == "unsupported_format"


@pytest.mark.parametrize("rate", [0, 1, 8000, 96000])
def test_rate_zero_is_invalid_audio(rate):
    assert reason_of(raw_wav(rate=rate, pcm=pcm(0.1, 16000))) == "bad_sample_rate"


def test_rejects_over_duration_cap():
    assert reason_of(make_wav(121, freq=None)) == "too_long"
    assert len(parse_wav(make_wav(120, freq=None)).samples) == 120 * 16000


def test_rejects_oversize_input():
    from nosolear.domain.audio import AudioLimits

    with pytest.raises(InvalidAudio) as exc:
        parse_wav(make_wav(1.0), AudioLimits(max_bytes=100))
    assert exc.value.reason == "too_large"


def test_rejects_empty_and_garbage():
    assert reason_of(b"") == "not_wav"
    assert reason_of(b"RIFF") == "not_wav"
    assert reason_of(b"not a wav") == "not_wav"
    not_wave = bytearray(make_wav(1.0))
    not_wave[8:12] = b"AVI "
    assert reason_of(bytes(not_wave)) == "not_wav"
    assert reason_of(raw_wav(rate=16000, pcm=b"")) == "empty"
    assert reason_of(raw_wav(rate=16000, pcm=b"\x00")) == "empty"


def test_odd_trailing_byte_dropped():
    rate = 16000
    audio = parse_wav(raw_wav(rate=rate, pcm=pcm(2, rate) + b"\x01"))
    assert len(audio.samples) == 2 * rate


def test_check_declared_length():
    check_declared_length(None)
    check_declared_length("10485760")
    with pytest.raises(InvalidAudio) as exc:
        check_declared_length("10485761")
    assert exc.value.reason == "too_large"
    for bad in ("abc", "-1"):
        with pytest.raises(InvalidAudio) as exc:
            check_declared_length(bad)
        assert exc.value.reason == "not_wav"


def test_invalid_audio_message_does_not_echo_input():
    with pytest.raises(InvalidAudio) as exc:
        check_declared_length("secret-value-123")
    assert "secret-value-123" not in str(exc.value)


def test_encode_wav_round_trips():
    x = np.array([0, 1, -1, 32767, -32768, 1234], dtype=np.int16)
    data = encode_wav(x)
    assert len(data) == 44 + 2 * len(x)
    audio = parse_wav(data)
    assert audio.sample_rate == 16000
    assert np.array_equal(audio.samples, x)


def test_duration_ms_rounds_down():
    assert duration_ms(16000, 16000) == 1000
    assert duration_ms(1, 16000) == 0
    assert duration_ms(47, 48000) == 0
    assert duration_ms(48000, 44100) == 1088


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x))))


@pytest.mark.parametrize("rate", sorted(ALLOWED_SAMPLE_RATES))
def test_resample_length_and_tone(rate):
    t = np.arange(rate) / rate
    x = 0.5 * np.sin(2 * np.pi * 440 * t)
    y = resample_to_16k(x, rate)
    assert abs(len(y) - 16000) <= 1
    assert abs(rms(y) - rms(x)) <= 0.1 * rms(x)


def test_resample_attenuates_above_nyquist_tone():
    rate = 48000
    t = np.arange(rate) / rate
    x = 0.5 * np.sin(2 * np.pi * 10_000 * t)
    y = resample_to_16k(x, rate)
    assert 20 * np.log10(rms(x) / max(rms(y), 1e-12)) >= 20


def test_resample_rejects_unlisted_rate_and_handles_empty():
    with pytest.raises(InvalidAudio) as exc:
        resample_to_16k(np.zeros(10), 8000)
    assert exc.value.reason == "bad_sample_rate"
    for rate in ALLOWED_SAMPLE_RATES:
        assert len(resample_to_16k(np.zeros(0), rate)) == 0
