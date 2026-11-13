"""mlx-whisper: the local `Transcriber` on Apple Silicon (ARCHITECTURE.md section 15).

The library loads only when a transcript is first requested, and the model is fetched at its
pinned revision first. Library errors become a literal `ProviderUnavailable`, with only the
exception's type name logged.
"""

import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol, cast

from nosolear.adapters.hf_models import ModelSpec, ensure_model
from nosolear.adapters.local_env import installed_version
from nosolear.adapters.model_specs import MLX_WHISPER
from nosolear.domain.errors import ProviderUnavailable
from nosolear.domain.results import parse_local_transcript
from nosolear.domain.speech import LOCAL, RawResult, Transcript

ADAPTER = "mlx_whisper"
ADAPTER_VERSION = 1
_LIBRARY = "mlx-whisper"
_FAILED = "The mlx_whisper transcriber failed on this recording"
_log = logging.getLogger(__name__)

Transcribe = Callable[..., Mapping[str, object]]


class _LibraryTranscribe(Protocol):
    def __call__(
        self, audio: str, *, path_or_hf_repo: str, language: str, word_timestamps: bool
    ) -> Mapping[str, object]: ...


def _default_call(spec: ModelSpec) -> Transcribe:
    def call(wav: str, *, language: str, word_timestamps: bool) -> Mapping[str, object]:
        from mlx_whisper import (  # pyright: ignore[reportMissingImports]
            transcribe,  # pyright: ignore[reportUnknownVariableType]
        )

        library = cast("_LibraryTranscribe", transcribe)
        return library(
            wav,
            path_or_hf_repo=str(ensure_model(spec)),
            language=language,
            word_timestamps=word_timestamps,
        )

    return call


def _as_list(value: object) -> list[object]:
    return cast("list[object]", value) if isinstance(value, list) else []


def _as_map(value: object) -> Mapping[str, object]:
    return cast("Mapping[str, object]", value) if isinstance(value, Mapping) else {}


def _words(result: Mapping[str, object]) -> list[dict[str, object]]:
    words: list[dict[str, object]] = []
    for segment in _as_list(result.get("segments")):
        for item in _as_list(_as_map(segment).get("words")):
            word = _as_map(item)
            words.append(
                {
                    "word": word.get("word"),
                    "start": word.get("start"),
                    "end": word.get("end"),
                    "probability": word.get("probability"),
                }
            )
    return words


class MlxWhisperTranscriber:
    layer = "raw"

    def __init__(
        self,
        *,
        spec: ModelSpec = MLX_WHISPER,
        transcribe: Transcribe | None = None,
    ) -> None:
        self._spec = spec
        self._call = transcribe if transcribe is not None else _default_call(spec)

    def transcribe(self, wav: Path) -> Transcript:
        try:
            result = self._call(str(wav), language="en", word_timestamps=True)
        except ProviderUnavailable:
            raise
        except Exception as exc:
            _log.warning("mlx-whisper failed: %s", type(exc).__name__)
            raise ProviderUnavailable(_FAILED) from None
        spec = self._spec
        text = result.get("text")
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
                    "text": text if isinstance(text, str) else "",
                    "words": _words(result),
                },
            )
        )
