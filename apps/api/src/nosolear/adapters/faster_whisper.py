"""faster-whisper: the local `Transcriber` for CTranslate2 Whisper models (ARCHITECTURE.md
section 15).

The library and its model load on the first `transcribe`, never at import. CUDA when torch reports
it, else CPU; `float16` on CUDA, `int8` on CPU. Library errors become a literal
`ProviderUnavailable`, with only the exception's type name logged.
"""

import logging
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Protocol, cast

from nosolear.adapters.hf_models import ModelSpec, disable_hf_telemetry, ensure_model
from nosolear.adapters.lazy_model import LazyModel
from nosolear.adapters.local_env import installed_version, torch_device
from nosolear.adapters.model_specs import FASTER_WHISPER
from nosolear.domain.errors import ProviderUnavailable
from nosolear.domain.results import parse_local_transcript
from nosolear.domain.speech import LOCAL, RawResult, Transcript

ADAPTER = "faster_whisper"
ADAPTER_VERSION = 1
_LIBRARY = "faster-whisper"
_FAILED = "The faster-whisper transcriber failed on this recording"
_log = logging.getLogger(__name__)


class _WordLike(Protocol):
    @property
    def word(self) -> str: ...

    @property
    def start(self) -> float: ...

    @property
    def end(self) -> float: ...

    @property
    def probability(self) -> float: ...


class _SegmentLike(Protocol):
    @property
    def text(self) -> str: ...

    @property
    def words(self) -> Sequence[_WordLike] | None: ...


class WhisperModelLike(Protocol):
    def transcribe(self, audio: str, **kwargs: object) -> tuple[Iterable[_SegmentLike], object]: ...


class _Constructor(Protocol):
    def __call__(self, model: str, *, device: str, compute_type: str) -> WhisperModelLike: ...


def _load(spec: ModelSpec) -> WhisperModelLike:
    disable_hf_telemetry()  # before any Hugging Face import
    from faster_whisper import (  # pyright: ignore[reportMissingImports]
        WhisperModel,  # pyright: ignore[reportUnknownVariableType]
    )

    cuda = torch_device() == "cuda"
    construct = cast("_Constructor", WhisperModel)
    return construct(
        str(ensure_model(spec)),
        device="cuda" if cuda else "cpu",
        compute_type="float16" if cuda else "int8",
    )


class FasterWhisperTranscriber:
    layer = "raw"

    def __init__(
        self,
        *,
        spec: ModelSpec = FASTER_WHISPER,
        model: LazyModel[WhisperModelLike] | None = None,
    ) -> None:
        self._spec = spec
        self._model = model if model is not None else LazyModel(lambda: _load(spec))

    def transcribe(self, wav: Path) -> Transcript:
        try:
            model = self._model.get()
            segments, _info = model.transcribe(
                str(wav),
                language="en",
                word_timestamps=True,
                beam_size=5,
                vad_filter=False,
            )
            done = list(segments)
        except ProviderUnavailable:
            raise
        except Exception as exc:
            _log.warning("faster-whisper failed: %s", type(exc).__name__)
            raise ProviderUnavailable(_FAILED) from None
        words = [
            {
                "word": word.word,
                "start": float(word.start),
                "end": float(word.end),
                "probability": float(word.probability),
            }
            for segment in done
            for word in segment.words or ()
        ]
        spec = self._spec
        return parse_local_transcript(
            RawResult(
                provider=LOCAL,
                provider_version=(
                    f"{_LIBRARY} {installed_version(_LIBRARY)}; {spec.repo_id}@{spec.revision[:12]}"
                ),
                adapter=ADAPTER,
                adapter_version=ADAPTER_VERSION,
                payload={
                    "engine": f"{_LIBRARY} {installed_version(_LIBRARY)}",
                    "model": {"repo_id": spec.repo_id, "revision": spec.revision},
                    "fillers_kept": False,
                    "text": "".join(segment.text for segment in done).strip(),
                    "words": words,
                },
            )
        )
