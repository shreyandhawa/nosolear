"""SQLite usage ledger (ARCHITECTURE.md section 11).

Every write runs under `BEGIN IMMEDIATE`, so the write lock is taken before the totals are read
and two reservations can never both see the same headroom.
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

from nosolear.domain.budget import Caps, Provider, Unit, Usage, fits, period_for
from nosolear.domain.errors import CapExceeded
from nosolear.persistence.models import format_utc
from nosolear.ports.clock import Clock
from nosolear.ports.ledger import LedgerError, Reservation


class SqliteUsageLedger:
    def __init__(self, engine: Engine, *, caps: Caps, clock: Clock) -> None:
        self._engine = engine
        self._caps = caps
        self._clock = clock

    def reserve(
        self, provider: Provider, unit: Unit, estimate: int, *, job_id: str | None = None
    ) -> Reservation:
        cap = self._caps.limit(provider, unit)
        if estimate < 0:
            raise ValueError("estimate must not be negative")
        now = self._clock.now()
        period = period_for(provider, unit, now)
        with self._immediate() as conn:
            recorded, reserved = _totals(conn, provider, unit, period)
            if not fits(cap, recorded, reserved, estimate):
                raise CapExceeded()
            result = conn.execute(
                text(
                    "INSERT INTO usage_ledger (provider, unit, state, estimate, actual, period, "
                    "job_id, created_at, settled_at) VALUES (:provider, :unit, 'reserved', "
                    ":estimate, NULL, :period, :job_id, :now, NULL)"
                ),
                {
                    "provider": provider.value,
                    "unit": unit.value,
                    "estimate": estimate,
                    "period": period,
                    "job_id": job_id,
                    "now": format_utc(now),
                },
            )
            reservation_id = result.lastrowid
        return Reservation(
            id=reservation_id, provider=provider, unit=unit, estimate=estimate, period=period
        )

    def record(self, reservation: Reservation, actual: int) -> None:
        if actual < 0:
            raise ValueError("actual must not be negative")
        with self._immediate() as conn:
            result = conn.execute(
                text(
                    "UPDATE usage_ledger SET state = 'recorded', actual = :actual, "
                    "settled_at = :now WHERE id = :id AND state = 'reserved'"
                ),
                {"actual": actual, "now": format_utc(self._clock.now()), "id": reservation.id},
            )
            if result.rowcount == 0:
                raise LedgerError("the reservation is not open")

    def release(self, reservation: Reservation) -> None:
        with self._immediate() as conn:
            result = conn.execute(
                text(
                    "UPDATE usage_ledger SET state = 'released', settled_at = :now "
                    "WHERE id = :id AND state = 'reserved'"
                ),
                {"now": format_utc(self._clock.now()), "id": reservation.id},
            )
            if result.rowcount == 0:
                raise LedgerError("the reservation is not open")

    def settle_open_reservations(self) -> int:
        with self._immediate() as conn:
            result = conn.execute(
                text(
                    "UPDATE usage_ledger SET state = 'recorded', actual = estimate, "
                    "settled_at = :now WHERE state = 'reserved'"
                ),
                {"now": format_utc(self._clock.now())},
            )
            return result.rowcount

    def usage(self, provider: Provider, unit: Unit) -> Usage:
        cap = self._caps.limit(provider, unit)
        period = period_for(provider, unit, self._clock.now())
        with self._engine.connect() as conn:
            recorded, reserved = _totals(conn, provider, unit, period)
        return Usage(
            provider=provider,
            unit=unit,
            period=period,
            recorded=recorded,
            reserved=reserved,
            cap=cap,
        )

    @contextmanager
    def _immediate(self) -> Generator[Connection]:
        """A connection inside `BEGIN IMMEDIATE`: commit on success, roll back on any error.

        pysqlite does not begin a transaction before a SELECT, so the BEGIN is issued by hand.
        """
        conn = self._engine.connect()
        try:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()


def _totals(conn: Connection, provider: Provider, unit: Unit, period: str) -> tuple[int, int]:
    """(recorded, reserved) for one provider, unit and period."""
    row = conn.execute(
        text(
            "SELECT "
            "COALESCE(SUM(CASE WHEN state = 'recorded' THEN actual END), 0), "
            "COALESCE(SUM(CASE WHEN state = 'reserved' THEN estimate END), 0) "
            "FROM usage_ledger WHERE provider = :provider AND unit = :unit AND period = :period"
        ),
        {"provider": provider.value, "unit": unit.value, "period": period},
    ).one()
    return int(row[0]), int(row[1])
