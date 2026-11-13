"""Real Whisper models on espeak-ng audio. Excluded by default; CI's local-models job runs them."""

import pytest
from textmetrics import word_error_rate
from wavs import wav_info

from nosolear.adapters.faster_whisper import FasterWhisperTranscriber
from nosolear.adapters.local_env import current_platform
from nosolear.adapters.mlx_whisper import MlxWhisperTranscriber
from nosolear.domain.transcriber_choice import Platform

SENTENCE = "The quick brown fox jumps over the lazy dog"


@pytest.mark.local_models
def test_faster_whisper_on_espeak_audio(espeak_wav):
    wav = espeak_wav(SENTENCE)
    t = FasterWhisperTranscriber().transcribe(wav)
    assert word_error_rate(SENTENCE, t.text) <= 0.5
    assert t.words and t.words[-1].end_ms <= wav_info(wav).seconds * 1000 + 500


@pytest.mark.local_models
@pytest.mark.skipif(
    current_platform() is not Platform.MACOS_ARM64, reason="mlx needs Apple Silicon"
)
def test_mlx_whisper_on_espeak_audio(espeak_wav):
    wav = espeak_wav(SENTENCE)
    t = MlxWhisperTranscriber().transcribe(wav)
    assert word_error_rate(SENTENCE, t.text) <= 0.5
    assert t.words and t.words[-1].end_ms <= wav_info(wav).seconds * 1000 + 500
