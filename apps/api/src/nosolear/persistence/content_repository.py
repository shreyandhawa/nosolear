"""SQLAlchemy adapter for the content store: seed rows are synced once per startup."""

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal, cast

from sqlalchemy import Engine, Row, insert, select, update

from nosolear.domain.content import ContentItem, ContentKind
from nosolear.persistence.models import content_items
from nosolear.ports.content_store import ContentConflict, SyncSummary


def _item(row: Row[Any]) -> ContentItem:
    source: Literal["seed", "coach"] = "coach" if row.source == "coach" else "seed"
    return ContentItem(
        id=row.id,
        kind=ContentKind(row.kind),
        text=row.text,
        target_keys=tuple(cast(list[str], json.loads(row.target_keys))),
        source=source,
    )


class ContentRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def sync_seed(self, items: Sequence[ContentItem], *, now: datetime) -> SyncSummary:
        """Inserts missing seed ids and retires seed ids that are gone. An existing id whose kind,
        text or keys changed raises `ContentConflict` before anything is written."""
        wanted = {item.id for item in items}
        with self._engine.begin() as conn:
            existing = {row.id: row for row in conn.execute(select(content_items))}
            for item in items:
                row = existing.get(item.id)
                if row is None:
                    continue
                stored = (row.kind, row.text, tuple(cast(list[str], json.loads(row.target_keys))))
                if stored != (item.kind.value, item.text, item.target_keys):
                    raise ContentConflict(f"content {item.id} changed; ids are immutable")
            added = 0
            for item in items:
                row = existing.get(item.id)
                if row is None:
                    conn.execute(
                        insert(content_items).values(
                            id=item.id,
                            kind=item.kind.value,
                            text=item.text,
                            target_keys=json.dumps(list(item.target_keys)),
                            source=item.source,
                            retired_at=None,
                        )
                    )
                    added += 1
                elif row.retired_at is not None:
                    conn.execute(
                        update(content_items)
                        .where(content_items.c.id == item.id)
                        .values(retired_at=None)
                    )
            retired = 0
            for row in existing.values():
                if row.source == "seed" and row.id not in wanted and row.retired_at is None:
                    conn.execute(
                        update(content_items)
                        .where(content_items.c.id == row.id)
                        .values(retired_at=now)
                    )
                    retired += 1
        return SyncSummary(added=added, retired=retired)

    def get(self, item_id: str) -> ContentItem | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(content_items).where(content_items.c.id == item_id)
            ).one_or_none()
        return None if row is None else _item(row)
