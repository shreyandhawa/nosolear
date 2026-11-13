"""The phone probe on Azure TTS audio of the calibration words. Live: needs an Azure key for the
clip (the model itself needs no key). Skipped when the local extra or espeak-ng is missing."""

from collections.abc import Callable
from pathlib import Path

import pytest

from nosolear.adapters.local_env import espeak_ng_path
from nosolear.adapters.wav2vec2_espeak import Wav2Vec2EspeakProbe
from nosolear.domain.phone_alignment import align_phones


@pytest.mark.live
@pytest.mark.parametrize("word", ["vest", "school", "think"])
def test_probe_on_tts_audio(tts_clip: Callable[..., Path], word: str):
    pytest.importorskip("transformers")
    exe = espeak_ng_path()
    if exe is None:
        pytest.skip("espeak-ng is not installed")
    r = Wav2Vec2EspeakProbe(espeak=exe).probe(tts_clip(word), reference_text=word)
    cost = sum(
        {"match": 0, "sub": 1, "ins": 1, "del": 1}[e.op] for e in align_phones(r.expected, r.heard)
    )
    assert r.heard and cost <= 0.5 * len(r.expected)
