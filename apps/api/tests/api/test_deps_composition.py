"""Every paid port the composition root builds is ordered cache -> retry -> metered -> raw."""

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest
from factories import FixedClock, make_settings
from fakes import FakePaidPort, FakeUsageLedger

from nosolear.api.deps import build_paid_ports
from nosolear.budget.compose import layers_of
from nosolear.domain.budget import DEFAULT_CAPS

T0 = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
TAIL = ["retry", "metered", "raw"]


def assert_port_order(name: str, port: object) -> None:
    """Fails unless `port` is exactly the stack the composition rules allow for `name`."""
    expected = ["cache", *TAIL] if name == "synthesizer" else TAIL
    assert layers_of(port) == expected, f"{name} is wrapped as {layers_of(port)}"


def assert_all_ports_ordered(ports: Mapping[str, object]) -> None:
    for name, port in ports.items():
        assert_port_order(name, port)


def test_every_paid_port_the_composition_root_builds_is_ordered(tmp_path):
    ports = build_paid_ports(
        make_settings(data_dir=tmp_path),
        ledger=FakeUsageLedger(DEFAULT_CAPS, FixedClock(T0)),
        clock=FixedClock(T0),
    )
    assert_all_ports_ordered(ports)


class _Wrapper:
    """A stand-in layer: `layers_of` only reads `layer` and `inner`."""

    def __init__(self, layer: str, inner: object) -> None:
        self.layer = layer
        self.inner = inner


def test_the_check_has_teeth():
    raw = FakePaidPort()
    misordered = _Wrapper("metered", _Wrapper("retry", raw))
    with pytest.raises(AssertionError):
        assert_port_order("pronunciation_scorer", misordered)
    with pytest.raises(AssertionError):
        assert_port_order("pronunciation_scorer", raw)
    with pytest.raises(AssertionError):
        assert_all_ports_ordered({"transcriber_azure": raw})
