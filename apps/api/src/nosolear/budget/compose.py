"""Composition order for every paid port: cache -> retry -> metered -> raw (ARCHITECTURE.md
section 11 and 15). Cache applies to TTS only. Each layer exposes `layer` and `inner`."""

from collections.abc import Callable
from typing import ClassVar

_NO_INNER = object()


class PortWrapper[T]:
    layer: ClassVar[str]
    inner: T

    def __init__(self, inner: T) -> None:
        self.inner = inner


def compose_paid_port[T](
    raw: T,
    *,
    metered: Callable[[T], T],
    retry: Callable[[T], T],
    cache: Callable[[T], T] | None = None,
) -> T:
    port = retry(metered(raw))
    if cache is not None:
        port = cache(port)
    return port


def layers_of(port: object) -> list[str]:
    """Layer names outermost first, following `.inner`; the raw adapter's own `layer` is last."""
    layers: list[str] = []
    current: object = port
    while True:
        layer = getattr(current, "layer", None)
        if not isinstance(layer, str):
            raise TypeError(f"{type(current).__name__} does not declare a composition layer")
        layers.append(layer)
        inner = getattr(current, "inner", _NO_INNER)
        if inner is _NO_INNER:
            return layers
        current = inner
