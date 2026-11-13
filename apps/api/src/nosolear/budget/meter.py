"""The metered layer: reserve before a paid call, settle after it (ARCHITECTURE.md section 11)."""

import functools
from collections.abc import Callable

from nosolear.domain.budget import Provider, Unit
from nosolear.domain.errors import RequestNotSent
from nosolear.ports.ledger import UsageLedger


class Meter:
    def __init__(
        self, ledger: UsageLedger, *, job_id: Callable[[], str | None] = lambda: None
    ) -> None:
        self._ledger = ledger
        self._job_id = job_id

    def call[R](
        self,
        provider: Provider,
        unit: Unit,
        estimate: int,
        fn: Callable[[], R],
        actual: Callable[[R], int],
    ) -> R:
        """Runs `fn` under a reservation. `CapExceeded` from the reserve means `fn` never runs."""
        reservation = self._ledger.reserve(provider, unit, estimate, job_id=self._job_id())
        try:
            result = fn()
        except RequestNotSent:
            self._ledger.release(reservation)
            raise
        except BaseException:
            self._ledger.record(reservation, estimate)
            raise
        try:
            measured = actual(result)
        except BaseException:
            self._ledger.record(reservation, estimate)
            raise
        self._ledger.record(reservation, measured)
        return result


def metered_method[**P, R](
    meter: Meter,
    *,
    provider: Provider,
    unit: Unit,
    estimate: Callable[P, int],
    actual: Callable[[R], int],
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Wraps one method so each call goes through `meter.call`, with `estimate` taking its args."""

    def decorate(fn: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            cost = estimate(*args, **kwargs)
            return meter.call(provider, unit, cost, lambda: fn(*args, **kwargs), actual)

        return wrapper

    return decorate
