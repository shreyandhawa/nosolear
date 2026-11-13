"""Runs every capability probe and stores what each one measured (`nosolear doctor --probe`).

One probe failing does not stop the others. A failure carries only the safe message its adapter
gave; the outcome is printed, so it must never hold a key or a provider body.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from nosolear.domain.errors import CapExceeded, ProviderUnavailable
from nosolear.domain.speech import ProviderCapabilities
from nosolear.ports.providers import CapabilityProbe
from nosolear.ports.stores import CapabilityWriter


@dataclass(frozen=True, slots=True)
class ProbeOutcome:
    adapter: str
    ok: bool
    message: str


def _summary(caps: ProviderCapabilities) -> str:
    return ", ".join(f"{key} {value}" for key, value in sorted(caps.capabilities.items()))


def probe_capabilities(
    *, probes: Sequence[CapabilityProbe], store: CapabilityWriter
) -> tuple[ProbeOutcome, ...]:
    outcomes: list[ProbeOutcome] = []
    for probe in probes:
        try:
            caps = probe.probe()
        except (CapExceeded, ProviderUnavailable) as exc:
            outcomes.append(ProbeOutcome(probe.adapter, False, exc.safe_message))
            continue
        store.add(caps)
        outcomes.append(ProbeOutcome(probe.adapter, True, _summary(caps)))
    return tuple(outcomes)
