"""Local-model surfaces: the errors a model download, espeak-ng and a local transcriber raise.

Each planted key goes into the library or process error that Nosolear must not repeat, so the
rendered error and its traceback must carry only the literal safe sentence.
"""

import subprocess
import traceback
from pathlib import Path
from typing import NoReturn

from wavs import write_wav

from nosolear.adapters.faster_whisper import FasterWhisperTranscriber
from nosolear.adapters.hf_models import ensure_model
from nosolear.adapters.lazy_model import LazyModel
from nosolear.adapters.model_specs import FASTER_WHISPER
from nosolear.adapters.wav2vec2_espeak import espeak_ipa
from nosolear.domain.errors import ProviderUnavailable
from security.planted import PLANTED_ANTHROPIC_KEY, PLANTED_AZURE_KEY, leak_surface


def _rendered(exc: BaseException) -> str:
    return str(exc) + repr(exc) + "".join(traceback.format_exception(exc))


@leak_surface
def model_download_error(tmp: Path) -> tuple[str, str]:
    """A download that fails with both planted keys in its message."""

    def download(**kwargs: object) -> str:
        raise OSError(f"401 for {PLANTED_AZURE_KEY} and {PLANTED_ANTHROPIC_KEY}")

    try:
        ensure_model(FASTER_WHISPER, download=download)
    except ProviderUnavailable as exc:
        return "model download error and traceback", _rendered(exc)
    raise AssertionError("a failed download did not raise")


@leak_surface
def espeak_failure(tmp: Path) -> tuple[str, str]:
    """espeak-ng exits non-zero and writes both planted keys to stderr."""

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            argv, 2, stdout="", stderr=f"bad {PLANTED_AZURE_KEY} {PLANTED_ANTHROPIC_KEY}"
        )

    try:
        espeak_ipa("school", executable=Path("/usr/bin/espeak-ng"), run=run)
    except ProviderUnavailable as exc:
        return "espeak-ng failure and traceback", _rendered(exc)
    raise AssertionError("a failing espeak-ng did not raise")


@leak_surface
def local_transcriber_library_error(tmp: Path) -> tuple[str, str]:
    """A library error that repeats an audio path and a planted key."""

    class BrokenModel:
        def transcribe(self, audio: object, **kwargs: object) -> NoReturn:
            raise RuntimeError(f"{PLANTED_ANTHROPIC_KEY} while reading {audio}")

    transcriber = FasterWhisperTranscriber(model=LazyModel(BrokenModel))
    try:
        transcriber.transcribe(write_wav(tmp / "leak.wav", 1))
    except ProviderUnavailable as exc:
        return "local transcriber error and traceback", _rendered(exc)
    raise AssertionError("a failing transcriber did not raise")
