import contextlib

import numpy as np
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra import numpy as hnp
from wavs import raw_wav

from nosolear.domain.audio import (
    ALLOWED_SAMPLE_RATES,
    WavAudio,
    encode_wav,
    parse_wav,
    resample_to_16k,
    to_16k,
)
from nosolear.domain.errors import InvalidAudio

RATES = sorted(ALLOWED_SAMPLE_RATES)
PREFIX = b"RIFF\x00\x00\x00\x00WAVE"


@given(st.binary(max_size=300))
def test_parse_never_raises_anything_but_invalid_audio(data):
    for blob in (data, PREFIX + data):
        with contextlib.suppress(InvalidAudio):
            parse_wav(blob)


@given(
    pcm=st.binary(max_size=2000),
    declared=st.integers(0, 2**32 - 1),
    riff_size=st.integers(0, 2**32 - 1),
    rate=st.integers(0, 200_000),
)
def test_header_lies_never_crash(pcm, declared, riff_size, rate):
    data = raw_wav(rate=rate, pcm=pcm, declared_data=declared, riff_size=riff_size)
    frames = min(declared, len(pcm)) // 2
    if rate not in ALLOWED_SAMPLE_RATES:
        expected = "bad_sample_rate"
    elif frames == 0:
        expected = "empty"
    else:
        expected = None
    if expected is None:
        assert len(parse_wav(data).samples) == frames
    else:
        try:
            parse_wav(data)
        except InvalidAudio as e:
            assert e.reason == expected
        else:
            raise AssertionError("expected InvalidAudio")


@given(st.binary(max_size=2000), st.sampled_from(RATES))
def test_frames_never_exceed_bytes_received(pcm, rate):
    data = raw_wav(rate=rate, pcm=pcm)
    try:
        audio = parse_wav(data)
    except InvalidAudio:
        return
    assert len(audio.samples) <= len(data) // 2


@given(st.sampled_from(RATES), st.integers(0, 20_000))
def test_resample_length_is_proportional(rate, n):
    out = resample_to_16k(np.zeros(n), rate)
    assert abs(len(out) - n * 16000 / rate) <= 1


@given(
    st.sampled_from(RATES),
    hnp.arrays(np.int16, st.integers(1, 3000)),
)
def test_to_16k_stays_in_int16_range_and_encodes(rate, samples):
    out = to_16k(WavAudio(sample_rate=rate, samples=samples))
    assert out.dtype == np.int16
    assert len(out) <= len(samples)
    if len(out):
        assert len(parse_wav(encode_wav(out)).samples) == len(out)


@given(hnp.arrays(np.int16, st.integers(1, 5000)))
def test_encode_parse_round_trip(samples):
    assert np.array_equal(parse_wav(encode_wav(samples)).samples, samples)
