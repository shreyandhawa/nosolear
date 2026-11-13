"""Local transcribers on Azure TTS audio. Live: needs an Azure key for the clip, never a model key.

Each library's test is skipped when the library is not installed (the `local` or `apple` extra).
CrisperWhisper runs only when it is the chosen transcriber, because its weights are non-commercial.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from textmetrics import word_error_rate

from nosolear.adapters.crisper_whisper import CrisperWhisperTranscriber
from nosolear.adapters.faster_whisper import FasterWhisperTranscriber
from nosolear.adapters.mlx_whisper import MlxWhisperTranscriber
from nosolear.settings import Settings

TEXT = "Yesterday I walked to the market and bought three green apples."


@pytest.mark.live
def test_faster_whisper_reaches_wer_on_tts(tts_clip: Callable[..., Path]):
    pytest.importorskip("faster_whisper")
    t = FasterWhisperTranscriber().transcribe(tts_clip(TEXT))
    assert word_error_rate(TEXT, t.text) <= 0.15


@pytest.mark.live
def test_mlx_whisper_reaches_wer_on_tts(tts_clip: Callable[..., Path]):
    pytest.importorskip("mlx_whisper")
    t = MlxWhisperTranscriber().transcribe(tts_clip(TEXT))
    assert word_error_rate(TEXT, t.text) <= 0.15


@pytest.mark.live
def test_crisper_whisper_is_opt_in(tts_clip: Callable[..., Path], live_settings: Settings):
    if live_settings.transcriber != "crisper_whisper":
        pytest.skip("opt-in: set NOSOLEAR_TRANSCRIBER=crisper_whisper")
    pytest.importorskip("transformers")
    t = CrisperWhisperTranscriber().transcribe(tts_clip(TEXT))
    assert word_error_rate(TEXT, t.text) <= 0.15 and t.fillers_kept
