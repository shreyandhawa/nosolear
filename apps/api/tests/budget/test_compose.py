from typing import ClassVar, cast

from fakes import FakePaidPort

from nosolear.budget.compose import PortWrapper, compose_paid_port, layers_of


class _Layer(PortWrapper[FakePaidPort]):
    layer: ClassVar[str]

    def __init__(self, inner: FakePaidPort) -> None:
        self.inner = inner


class Cache(_Layer):
    layer = "cache"


class Retry(_Layer):
    layer = "retry"


class Metered(_Layer):
    layer = "metered"


# The wrappers are duck-typed layers; `cast` tells pyright they stand in for the port type.
def _cache(port: FakePaidPort) -> FakePaidPort:
    return cast(FakePaidPort, Cache(port))


def _retry(port: FakePaidPort) -> FakePaidPort:
    return cast(FakePaidPort, Retry(port))


def _metered(port: FakePaidPort) -> FakePaidPort:
    return cast(FakePaidPort, Metered(port))


def test_compose_order_is_cache_retry_metered_raw():
    raw = FakePaidPort()
    port = compose_paid_port(raw, metered=_metered, retry=_retry, cache=_cache)
    assert layers_of(port) == ["cache", "retry", "metered", "raw"]


def test_without_cache_order_is_retry_metered_raw():
    port = compose_paid_port(FakePaidPort(), metered=_metered, retry=_retry)
    assert layers_of(port) == ["retry", "metered", "raw"]


def test_layers_of_raw_only():
    assert layers_of(FakePaidPort()) == ["raw"]
