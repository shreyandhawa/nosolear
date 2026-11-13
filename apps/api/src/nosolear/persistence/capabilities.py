"""SQLAlchemy adapter for the provider capability records, plus a read-only reader for `doctor`."""

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import Engine, select

from nosolear.domain.speech import ProviderCapabilities
from nosolear.persistence.models import provider_capabilities


def _record(
    *,
    provider: str,
    adapter: str,
    adapter_version: int,
    provider_version: str,
    region: str | None,
    locale: str | None,
    capabilities_json: str,
    probed_at: datetime,
) -> ProviderCapabilities:
    decoded: dict[str, object] = dict(json.loads(capabilities_json))
    return ProviderCapabilities(
        provider=provider,
        adapter=adapter,
        adapter_version=adapter_version,
        provider_version=provider_version,
        region=region,
        locale=locale,
        capabilities=decoded,
        probed_at=probed_at.astimezone(UTC),
    )


def newest_per_adapter(records: Iterable[ProviderCapabilities]) -> list[ProviderCapabilities]:
    """One record per (provider, adapter): the one probed last. Ties keep the first seen."""
    newest: dict[tuple[str, str], ProviderCapabilities] = {}
    for record in records:
        key = (record.provider, record.adapter)
        held = newest.get(key)
        if held is None or record.probed_at > held.probed_at:
            newest[key] = record
    return list(newest.values())


class CapabilityRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, caps: ProviderCapabilities) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                provider_capabilities.insert().values(
                    provider=caps.provider,
                    adapter=caps.adapter,
                    adapter_version=caps.adapter_version,
                    provider_version=caps.provider_version,
                    region=caps.region,
                    locale=caps.locale,
                    capabilities_json=json.dumps(
                        dict(caps.capabilities), sort_keys=True, separators=(",", ":")
                    ),
                    probed_at=caps.probed_at,
                )
            )

    def latest(self, provider: str, adapter: str) -> ProviderCapabilities | None:
        stmt = (
            select(provider_capabilities)
            .where(
                provider_capabilities.c.provider == provider,
                provider_capabilities.c.adapter == adapter,
            )
            .order_by(provider_capabilities.c.probed_at.desc(), provider_capabilities.c.id.desc())
            .limit(1)
        )
        with self._engine.connect() as conn:
            row = conn.execute(stmt).one_or_none()
        if row is None:
            return None
        return _record(
            provider=row.provider,
            adapter=row.adapter,
            adapter_version=row.adapter_version,
            provider_version=row.provider_version,
            region=row.region,
            locale=row.locale,
            capabilities_json=row.capabilities_json,
            probed_at=row.probed_at,
        )

    def latest_all(self) -> list[ProviderCapabilities]:
        with self._engine.connect() as conn:
            rows = conn.execute(select(provider_capabilities)).all()
        return newest_per_adapter(
            _record(
                provider=row.provider,
                adapter=row.adapter,
                adapter_version=row.adapter_version,
                provider_version=row.provider_version,
                region=row.region,
                locale=row.locale,
                capabilities_json=row.capabilities_json,
                probed_at=row.probed_at,
            )
            for row in rows
        )


def read_capability_records(conn: sqlite3.Connection) -> list[ProviderCapabilities]:
    """Newest-per-adapter records over an open read-only connection. Raises `sqlite3.Error` when
    the table is missing; the caller decides what that means (see `api/deps.read_usage`)."""
    rows = conn.execute(
        "SELECT provider, adapter, adapter_version, provider_version, region, locale,"
        " capabilities_json, probed_at FROM provider_capabilities ORDER BY id"
    ).fetchall()
    return newest_per_adapter(
        _record(
            provider=str(provider),
            adapter=str(adapter),
            adapter_version=int(adapter_version),
            provider_version=str(provider_version),
            region=None if region is None else str(region),
            locale=None if locale is None else str(locale),
            capabilities_json=str(capabilities_json),
            probed_at=datetime.fromisoformat(str(probed_at)),
        )
        for (
            provider,
            adapter,
            adapter_version,
            provider_version,
            region,
            locale,
            capabilities_json,
            probed_at,
        ) in rows
    )
