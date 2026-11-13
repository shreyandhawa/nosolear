"""The wav2vec2 phone probe: what was heard, as phones, next to what the reference should sound like
(ARCHITECTURE.md section 15).

espeak-ng turns the reference text into IPA (a fixed argv, the text on stdin, never a shell). A
wav2vec2 CTC model, pinned and loaded from its local snapshot with `weights_only=True`, hears the
16 kHz WAV as phones. Both sides go through `domain/phones.py`, and an unmapped symbol is a
`ProviderUnavailable`, never a guess. Nothing is metered or retried: the probe is local.
"""

import json
import logging
import subprocess
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol, cast

import numpy as np
from numpy.typing import NDArray

from nosolear.adapters.hf_models import disable_hf_telemetry, ensure_model
from nosolear.adapters.lazy_model import LazyModel
from nosolear.adapters.local_env import installed_version, torch_device
from nosolear.adapters.model_specs import WAV2VEC2_ESPEAK
from nosolear.adapters.wav_samples import SAMPLE_RATE, read_16k_mono
from nosolear.domain.errors import ProviderUnavailable
from nosolear.domain.phones import UnmappedSymbol
from nosolear.domain.results.phone_probe import parse_phone_probe
from nosolear.domain.speech import LOCAL, PhoneProbeResult, RawResult

ADAPTER = "wav2vec2_espeak"
ADAPTER_VERSION = 1
ESPEAK_ARGS = ("-q", "-v", "en-us", "--ipa", "--sep=_", "--stdin")
MAX_REFERENCE_CHARS = 1000
SPECIAL_TOKENS = frozenset({"<s>", "</s>", "<pad>"})
"""Dropped from the output. `<unk>` is kept, so an unknown phone fails loudly downstream."""

_ESPEAK_FAILED = "espeak-ng failed; check it is installed and runs"
_FAILED = "The phone probe failed on this recording"
_UNMAPPED = "The phone probe heard a sound symbol Nosolear can't map yet"
_TIMEOUT_S = 10
_log = logging.getLogger(__name__)

Run = Callable[..., subprocess.CompletedProcess[str]]


class PhoneRecognizer(Protocol):
    def tokens(self, wav: Path) -> list[str]: ...


def _check_text(text: str) -> None:
    if not text.strip():
        raise ValueError("the reference text is empty")
    if len(text) > MAX_REFERENCE_CHARS:
        raise ValueError(f"the reference text is longer than {MAX_REFERENCE_CHARS} characters")
    if any(unicodedata.category(char) == "Cc" for char in text):
        raise ValueError("the reference text contains a control character")


def espeak_ipa(text: str, *, executable: Path, run: Run = subprocess.run) -> str:
    """The IPA for `text`, with espeak-ng's `_` between phones and spaces between words."""
    _check_text(text)
    try:
        done = run(
            [str(executable), *ESPEAK_ARGS],
            input=text,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        raise ProviderUnavailable(_ESPEAK_FAILED) from None
    if done.returncode != 0:
        raise ProviderUnavailable(_ESPEAK_FAILED)
    return done.stdout.strip()


def ctc_greedy_decode(
    ids: Sequence[int],
    vocab: Mapping[int, str],
    *,
    blank_id: int,
    special: frozenset[str],
) -> list[str]:
    """Greedy CTC: collapse repeated ids, then drop the blank and the special tokens."""
    collapsed: list[int] = []
    for index in ids:
        if not collapsed or collapsed[-1] != index:
            collapsed.append(index)
    tokens: list[str] = []
    for index in collapsed:
        if index == blank_id:
            continue
        token = vocab.get(index)
        if token is None:
            raise ValueError("the model produced an id that is not in its vocabulary")
        if token not in special:
            tokens.append(token)
    return tokens


class _Tensor(Protocol):
    def to(self, device: str) -> _Tensor: ...
    def argmax(self, dim: int) -> _Tensor: ...
    def __getitem__(self, index: int) -> _Tensor: ...
    def tolist(self) -> list[int]: ...


class _Batch(Protocol):
    @property
    def input_values(self) -> _Tensor: ...


class _Output(Protocol):
    @property
    def logits(self) -> _Tensor: ...


class _Model(Protocol):
    def to(self, device: str) -> _Model: ...
    def eval(self) -> _Model: ...
    def __call__(self, input_values: _Tensor) -> _Output: ...


class _Extractor(Protocol):
    def __call__(
        self, samples: NDArray[np.float32], *, sampling_rate: int, return_tensors: str
    ) -> _Batch: ...


class _ExtractorClass(Protocol):
    def from_pretrained(self, path: str) -> _Extractor: ...


class _ModelClass(Protocol):
    def from_pretrained(
        self, path: str, *, use_safetensors: bool, weights_only: bool
    ) -> _Model: ...


class _Torch(Protocol):
    def no_grad(self) -> AbstractContextManager[None]: ...


class _Wav2Vec2Recognizer:
    def __init__(
        self,
        *,
        extractor: _Extractor,
        model: _Model,
        torch_module: _Torch,
        device: str,
        vocab: Mapping[int, str],
        blank_id: int,
    ) -> None:
        self._extractor = extractor
        self._model = model
        self._torch = torch_module
        self._device = device
        self._vocab = vocab
        self._blank_id = blank_id

    def tokens(self, wav: Path) -> list[str]:
        batch = self._extractor(read_16k_mono(wav), sampling_rate=SAMPLE_RATE, return_tensors="pt")
        with self._torch.no_grad():
            logits = self._model(batch.input_values.to(self._device)).logits
        ids = logits.argmax(-1)[0].tolist()
        return ctc_greedy_decode(ids, self._vocab, blank_id=self._blank_id, special=SPECIAL_TOKENS)


def _load_recognizer() -> PhoneRecognizer:
    """The pinned checkpoint, loaded from its local snapshot. Imports happen here, on first use."""
    disable_hf_telemetry()  # before any Hugging Face import
    import torch  # pyright: ignore[reportMissingImports]
    from transformers import (  # pyright: ignore[reportMissingImports]
        Wav2Vec2FeatureExtractor,  # pyright: ignore[reportUnknownVariableType]
        Wav2Vec2ForCTC,  # pyright: ignore[reportUnknownVariableType]
    )

    local = ensure_model(WAV2VEC2_ESPEAK)
    device = torch_device()
    extractor_class = cast("_ExtractorClass", Wav2Vec2FeatureExtractor)
    model_class = cast("_ModelClass", Wav2Vec2ForCTC)
    model = model_class.from_pretrained(str(local), use_safetensors=False, weights_only=True)
    raw_vocab: object = json.loads((local / "vocab.json").read_text(encoding="utf-8"))
    config: object = json.loads((local / "config.json").read_text(encoding="utf-8"))
    if not isinstance(raw_vocab, dict) or not isinstance(config, dict):
        raise ValueError("the phone probe snapshot is not readable")
    vocab = {int(index): str(token) for token, index in cast("dict[str, int]", raw_vocab).items()}
    blank = cast("dict[str, int]", config).get("pad_token_id", 0)
    return _Wav2Vec2Recognizer(
        extractor=extractor_class.from_pretrained(str(local)),
        model=model.to(device).eval(),
        torch_module=cast("_Torch", torch),
        device=device,
        vocab=vocab,
        blank_id=blank,
    )


class Wav2Vec2EspeakProbe:
    layer = "raw"

    def __init__(
        self,
        *,
        espeak: Path,
        recognizer: LazyModel[PhoneRecognizer] | None = None,
        run: Run = subprocess.run,
    ) -> None:
        self._espeak = espeak
        self._recognizer = recognizer if recognizer is not None else LazyModel(_load_recognizer)
        self._run = run
        self._version: str | None = None

    def _espeak_version(self) -> str:
        if self._version is None:
            try:
                done = self._run(
                    [str(self._espeak), "--version"],
                    capture_output=True,
                    text=True,
                    timeout=_TIMEOUT_S,
                    check=False,
                )
            except OSError, subprocess.SubprocessError:
                raise ProviderUnavailable(_ESPEAK_FAILED) from None
            if done.returncode != 0:
                raise ProviderUnavailable(_ESPEAK_FAILED)
            lines = done.stdout.strip().splitlines()
            self._version = lines[0].strip() if lines else "unknown"
        return self._version

    def probe(self, wav: Path, *, reference_text: str) -> PhoneProbeResult:
        ipa = espeak_ipa(reference_text, executable=self._espeak, run=self._run)
        version = self._espeak_version()
        try:
            heard = self._recognizer.get().tokens(wav)
        except ProviderUnavailable:
            raise
        except Exception as exc:
            _log.warning("phone probe failed: %s", type(exc).__name__)
            raise ProviderUnavailable(_FAILED) from None
        model = WAV2VEC2_ESPEAK
        raw = RawResult(
            provider=LOCAL,
            provider_version=(
                f"espeak-ng {version}; {model.repo_id}@{model.revision[:12]}"
                f" (transformers {installed_version('transformers')})"
            ),
            adapter=ADAPTER,
            adapter_version=ADAPTER_VERSION,
            payload={
                "espeak_ipa": ipa,
                "espeak_version": version,
                "heard_tokens": heard,
                "model": {"repo_id": model.repo_id, "revision": model.revision},
            },
        )
        try:
            return parse_phone_probe(raw)
        except UnmappedSymbol as exc:
            _log.warning("phone probe met an unmapped symbol %r", exc.symbol)
            raise ProviderUnavailable(_UNMAPPED) from None
