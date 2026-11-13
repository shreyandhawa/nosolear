"""Runs every capability probe and stores what each one measured (`nosolear doctor --probe`).

One probe failing does not stop the others. A failure carries only the safe message its adapter
gave; the outcome is printed, so it must never hold a key or a provider body.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from nosolear.domain.errors import NosolearError
from nosolear.domain.speech import ProviderCapabilities
from nosolear.ports.providers import CapabilityProbe
from nosolear.ports.stores import CapabilityWriter

logger = logging.getLogger(__name__)
UNEXPECTED_PROBE_FAILURE = "The probe failed unexpectedly"


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
        except NosolearError as exc:
            outcomes.append(ProbeOutcome(probe.adapter, False, exc.safe_message))
            continue
        except Exception as exc:
            # Its message may hold a key or a provider body: log the type name only.
            logger.warning("probe %s failed unexpectedly (%s)", probe.adapter, type(exc).__name__)
            outcomes.append(ProbeOutcome(probe.adapter, False, UNEXPECTED_PROBE_FAILURE))
            continue
        store.add(caps)
        outcomes.append(ProbeOutcome(probe.adapter, True, _summary(caps)))
    return tuple(outcomes)
