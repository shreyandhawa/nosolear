"""Pinned Hugging Face model downloads (ARCHITECTURE.md section 15).

Every download names a full commit SHA and an allow-list of files, so a configured model is never
fetched unpinned. Telemetry is switched off before any Hugging Face import. The downloader is
injectable, so tests never touch the network.
"""

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from nosolear.domain.errors import ProviderUnavailable

_REVISION = re.compile(r"[0-9a-f]{40}")
_REPO_ID = re.compile(r"[\w.-]+/[\w.-]+")


@dataclass(frozen=True, slots=True)
class ModelSpec:
    label: str
    repo_id: str
    revision: str
    allow_patterns: tuple[str, ...]
    gated: bool = False

    def __post_init__(self) -> None:
        if not _REVISION.fullmatch(self.revision):
            raise ValueError("a model revision must be a full 40-character commit SHA")
        if not _REPO_ID.fullmatch(self.repo_id):
            raise ValueError("a model repo id must look like owner/name")


class _Downloader(Protocol):
    def __call__(self, *, repo_id: str, revision: str, allow_patterns: list[str]) -> str: ...


def disable_hf_telemetry() -> None:
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def _snapshot_download(*, repo_id: str, revision: str, allow_patterns: list[str]) -> str:
    from huggingface_hub import (  # pyright: ignore[reportMissingImports]
        snapshot_download,  # pyright: ignore[reportUnknownVariableType]
    )

    download = cast("_Downloader", snapshot_download)
    return download(repo_id=repo_id, revision=revision, allow_patterns=allow_patterns)


def _failure(spec: ModelSpec) -> str:
    if spec.gated:
        return (
            f"Couldn't download the {spec.label} model. Accept the model's licence on"
            " huggingface.co and run `hf auth login`, then run it again."
        )
    return (
        f"Couldn't download the {spec.label} model. Check your network connection and run it again."
    )


def ensure_model(spec: ModelSpec, *, download: Callable[..., str] | None = None) -> Path:
    """The local snapshot directory for `spec`, downloaded on first use at its pinned revision."""
    disable_hf_telemetry()
    fetch: Callable[..., str] = download if download is not None else _snapshot_download
    try:
        local = fetch(
            repo_id=spec.repo_id,
            revision=spec.revision,
            allow_patterns=list(spec.allow_patterns),
        )
    except Exception:
        raise ProviderUnavailable(_failure(spec)) from None
    return Path(local)
