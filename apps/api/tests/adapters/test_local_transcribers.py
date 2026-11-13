import logging
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pytest
from wavs import write_wav

from nosolear.adapters import crisper_whisper, faster_whisper, mlx_whisper
from nosolear.adapters.crisper_whisper import CrisperWhisperTranscriber
from nosolear.adapters.faster_whisper import FasterWhisperTranscriber
from nosolear.adapters.lazy_model import LazyModel
from nosolear.adapters.mlx_whisper import MlxWhisperTranscriber
from nosolear.domain.errors import ProviderUnavailable


@dataclass
class FakeWord:
    word: str
    start: float
    end: float
    probability: float


@dataclass
class FakeSegment:
    words: list[FakeWord]
    text: str = ""


@dataclass
class FakeWhisperModel:
    segments: list[FakeSegment]
    kwargs: dict[str, Any] = field(default_factory=dict)
    error: Exception | None = None
    audio: Any = None

    def transcribe(self, audio: Any, **kwargs: Any) -> tuple[list[FakeSegment], object]:
        if self.error is not None:
            raise self.error
        self.audio = audio
        self.kwargs = kwargs
        return self.segments, None


def test_faster_whisper_passes_language_and_word_timestamps(tmp_path):
    model = FakeWhisperModel(segments=[FakeSegment(words=[FakeWord(" vest", 0.1, 0.5, 0.9)])])
    t = FasterWhisperTranscriber(model=LazyModel(lambda: model)).transcribe(
        write_wav(tmp_path / "a.wav", 1)
    )
    # an array, never a path: faster-whisper decodes a path with PyAV, which it breaks on
    assert model.audio.dtype == np.float32 and model.audio.shape == (16000,)
    assert model.kwargs == {
        "language": "en",
        "word_timestamps": True,
        "beam_size": 5,
        "vad_filter": False,
    }
    assert t.words[0].text == "vest" and t.words[0].start_ms == 100
    assert t.raw.adapter == "faster_whisper" and not t.fillers_kept


def test_library_error_is_provider_unavailable_without_its_message(tmp_path, caplog):
    model = FakeWhisperModel(segments=[], error=RuntimeError("secret detail /private/x.wav"))
    transcriber = FasterWhisperTranscriber(model=LazyModel(lambda: model))
    caplog.set_level(logging.WARNING)
    with pytest.raises(ProviderUnavailable, match="The faster-whisper transcriber failed") as info:
        transcriber.transcribe(write_wav(tmp_path / "a.wav", 1))
    assert info.value.__cause__ is None and info.value.__suppress_context__
    assert "secret detail" not in str(info.value)
    assert "secret detail" not in caplog.text and "RuntimeError" in caplog.text


def test_mlx_maps_segments(tmp_path):
    seen: dict[str, Any] = {}

    def fake_transcribe(wav: Any, **kwargs: Any) -> dict[str, object]:
        seen["wav"] = wav
        seen.update(kwargs)
        return {
            "text": " vest",
            "segments": [
                {"words": [{"word": " vest", "start": 0.1, "end": 0.5, "probability": 0.9}]}
            ],
        }

    wav = write_wav(tmp_path / "a.wav", 1)
    t = MlxWhisperTranscriber(transcribe=fake_transcribe).transcribe(wav)
    # an array, never a path: mlx-whisper runs ffmpeg on a path
    audio = seen.pop("wav")
    assert audio.dtype == np.float32 and audio.shape == (16000,)
    assert seen == {"language": "en", "word_timestamps": True}
    assert t.words[0].text == "vest" and t.words[0].end_ms == 500
    assert t.raw.adapter == "mlx_whisper" and not t.fillers_kept


def test_mlx_library_error_is_provider_unavailable(tmp_path):
    def broken(wav: str, **kwargs: Any) -> dict[str, object]:
        raise ValueError("bad weights at /secret/path")

    with pytest.raises(ProviderUnavailable, match="The mlx_whisper transcriber failed") as info:
        MlxWhisperTranscriber(transcribe=broken).transcribe(write_wav(tmp_path / "a.wav", 1))
    assert "secret" not in str(info.value)


class FakePipeline:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.calls: list[str] = []

    def __call__(self, audio: str) -> dict[str, object]:
        self.calls.append(audio)
        return self.result


def test_crisper_keeps_fillers(tmp_path):
    pipeline = FakePipeline(
        {
            "text": " um I",
            "chunks": [
                {"text": " um", "timestamp": (0.0, 0.3)},
                {"text": " I", "timestamp": (0.4, 0.5)},
            ],
        }
    )
    wav = write_wav(tmp_path / "a.wav", 1)
    t = CrisperWhisperTranscriber(pipeline=LazyModel(lambda: pipeline)).transcribe(wav)
    assert [w.text for w in t.words] == ["um", "I"]
    assert t.fillers_kept is True and t.raw.adapter == "crisper_whisper"
    assert pipeline.calls == [str(wav)]


def test_crisper_word_without_an_end_time_keeps_its_start(tmp_path):
    pipeline = FakePipeline({"text": "ok", "chunks": [{"text": "ok", "timestamp": (0.2, None)}]})
    t = CrisperWhisperTranscriber(pipeline=LazyModel(lambda: pipeline)).transcribe(
        write_wav(tmp_path / "a.wav", 1)
    )
    assert (t.words[0].start_ms, t.words[0].end_ms) == (200, 200)


def test_adapters_declare_the_raw_layer_and_versions():
    for module in (faster_whisper, mlx_whisper, crisper_whisper):
        assert module.ADAPTER_VERSION == 1
    assert faster_whisper.ADAPTER == "faster_whisper"
    assert mlx_whisper.ADAPTER == "mlx_whisper"
    assert crisper_whisper.ADAPTER == "crisper_whisper"
    for cls in (FasterWhisperTranscriber, MlxWhisperTranscriber, CrisperWhisperTranscriber):
        assert cls.layer == "raw"


def test_constructing_imports_nothing():
    code = (
        "import sys\n"
        "from nosolear.adapters.faster_whisper import FasterWhisperTranscriber\n"
        "from nosolear.adapters.mlx_whisper import MlxWhisperTranscriber\n"
        "from nosolear.adapters.crisper_whisper import CrisperWhisperTranscriber\n"
        "FasterWhisperTranscriber(); MlxWhisperTranscriber(); CrisperWhisperTranscriber()\n"
        "heavy = ['torch', 'transformers', 'faster_whisper', 'mlx', 'mlx_whisper',"
        " 'huggingface_hub', 'ctranslate2']\n"
        "print([m for m in heavy if m in sys.modules])\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"
