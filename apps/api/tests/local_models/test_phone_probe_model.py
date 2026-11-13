"""The real wav2vec2 phone probe on espeak-ng audio. Excluded by default; CI's local-models job."""

import pytest

from nosolear.adapters.local_env import espeak_ng_path
from nosolear.adapters.wav2vec2_espeak import Wav2Vec2EspeakProbe
from nosolear.domain.phone_alignment import align_phones


@pytest.mark.local_models
@pytest.mark.parametrize("word", ["stop", "vest", "think"])
def test_probe_on_espeak_audio(espeak_wav, word):
    exe = espeak_ng_path()
    if exe is None:
        pytest.skip("espeak-ng is not installed")
    r = Wav2Vec2EspeakProbe(espeak=exe).probe(espeak_wav(word), reference_text=word)
    cost = sum(
        {"match": 0, "sub": 1, "ins": 1, "del": 1}[e.op] for e in align_phones(r.expected, r.heard)
    )
    assert r.heard and cost <= 0.5 * len(r.expected)
