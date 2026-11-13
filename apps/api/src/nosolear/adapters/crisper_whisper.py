"""CrisperWhisper: the opt-in local `Transcriber` that keeps fillers (ARCHITECTURE.md section 15).

It is never chosen by `auto`. Its weights are CC BY-NC 4.0 (see THIRD_PARTY_NOTICES). The
transformers ASR pipeline loads on the first `transcribe`, from the pinned local snapshot, with
safetensors only. Library errors become a literal `ProviderUnavailable`, with only the exception's
type name logged.
"""

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

from nosolear.adapters.hf_models import disable_hf_telemetry, ensure_model
from nosolear.adapters.lazy_model import LazyModel
from nosolear.adapters.local_env import installed_version, torch_device
from nosolear.adapters.model_specs import CRISPER_WHISPER
from nosolear.domain.errors import ProviderUnavailable
from nosolear.domain.results import parse_local_transcript
from nosolear.domain.speech import LOCAL, RawResult, Transcript

ADAPTER = "crisper_whisper"
ADAPTER_VERSION = 1
_LIBRARY = "transformers"
_FAILED = "The crisper_whisper transcriber failed on this recording"
_log = logging.getLogger(__name__)


class AsrPipelineLike(Protocol):
    def __call__(self, audio: str) -> Mapping[str, object]: ...


class _PipelineFactory(Protocol):
    def __call__(
        self,
        task: str,
        *,
        model: str,
        device: str,
        dtype: str,
        return_timestamps: str,
        model_kwargs: Mapping[str, object],
    ) -> AsrPipelineLike: ...


def _load() -> AsrPipelineLike:
    disable_hf_telemetry()  # before any Hugging Face import
    from transformers import (  # pyright: ignore[reportMissingImports]
        pipeline,  # pyright: ignore[reportUnknownVariableType]
    )

    device = torch_device()
    half = device in ("mps", "cuda")
    factory = cast("_PipelineFactory", pipeline)
    return factory(
        "automatic-speech-recognition",
        model=str(ensure_model(CRISPER_WHISPER)),
        device=device,
        dtype="float16" if half else "float32",
        return_timestamps="word",
        model_kwargs={"use_safetensors": True},
    )


def _as_list(value: object) -> list[object]:
    return cast("list[object]", value) if isinstance(value, list) else []


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _words(result: Mapping[str, object]) -> list[dict[str, object]]:
    words: list[dict[str, object]] = []
    for item in _as_list(result.get("chunks")):
        if not isinstance(item, Mapping):
            continue
        chunk = cast("Mapping[str, object]", item)
        span = chunk.get("timestamp")
        if not isinstance(span, tuple | list) or len(cast("Sequence[object]", span)) != 2:
            continue
        start = _number(cast("Sequence[object]", span)[0])
        end = _number(cast("Sequence[object]", span)[1])
        if start is None:
            continue
        words.append(
            {
                "word": chunk.get("text"),
                "start": start,
                "end": start if end is None else end,
                "probability": None,
            }
        )
    return words


class CrisperWhisperTranscriber:
    layer = "raw"

    def __init__(self, *, pipeline: LazyModel[AsrPipelineLike] | None = None) -> None:
        self._pipeline = pipeline if pipeline is not None else LazyModel(_load)

    def transcribe(self, wav: Path) -> Transcript:
        try:
            asr = self._pipeline.get()
            result = asr(str(wav))
        except ProviderUnavailable:
            raise
        except Exception as exc:
            _log.warning("crisper-whisper failed: %s", type(exc).__name__)
            raise ProviderUnavailable(_FAILED) from None
        text = result.get("text")
        provider_version = (
            f"{_LIBRARY} {installed_version(_LIBRARY)}; "
            f"{CRISPER_WHISPER.repo_id}@{CRISPER_WHISPER.revision[:12]}"
        )
        return parse_local_transcript(
            RawResult(
                provider=LOCAL,
                provider_version=provider_version,
                adapter=ADAPTER,
                adapter_version=ADAPTER_VERSION,
                payload={
                    "engine": f"{_LIBRARY} {installed_version(_LIBRARY)}",
                    "model": {
                        "repo_id": CRISPER_WHISPER.repo_id,
                        "revision": CRISPER_WHISPER.revision,
                    },
                    "fillers_kept": True,
                    "text": text if isinstance(text, str) else "",
                    "words": _words(result),
                },
            )
        )
