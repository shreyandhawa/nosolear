"""The content store port: seed rows are synced at startup; attempts refer to them by id.
Adapters live in `persistence`."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from nosolear.domain.content import ContentItem


class ContentConflict(ValueError):
    """A seed id whose kind, text or keys changed. Ids are immutable, so this is refused."""


@dataclass(frozen=True, slots=True)
class SyncSummary:
    added: int
    retired: int


class ContentStore(Protocol):
    def sync_seed(self, items: Sequence[ContentItem], *, now: datetime) -> SyncSummary: ...

    def get(self, item_id: str) -> ContentItem | None: ...
