"""The usage ledger port: every paid call reserves against a cap before it is made."""

from dataclasses import dataclass
from typing import Protocol

from nosolear.domain.budget import Provider, Unit, Usage


class LedgerError(ValueError):
    """A reservation was settled twice, or settled after it was released or recorded."""


@dataclass(frozen=True, slots=True)
class Reservation:
    id: int
    provider: Provider
    unit: Unit
    estimate: int
    period: str


class UsageLedger(Protocol):
    def reserve(
        self, provider: Provider, unit: Unit, estimate: int, *, job_id: str | None = None
    ) -> Reservation:
        """Raises `CapExceeded` (and writes nothing) when the estimate does not fit the cap."""
        ...

    def record(self, reservation: Reservation, actual: int) -> None:
        """Settles an open reservation at `actual`. Raises `LedgerError` if it is not open."""
        ...

    def release(self, reservation: Reservation) -> None:
        """Frees an open reservation. Raises `LedgerError` if it is not open."""
        ...

    def settle_open_reservations(self) -> int:
        """Startup: every open reservation is recorded at its estimate. Returns the count."""
        ...

    def usage(self, provider: Provider, unit: Unit) -> Usage:
        """Totals for the current period."""
        ...
