"""Ports for feedback: the observations of one session and the stored feedback items.

Adapters: `persistence`.
"""

from dataclasses import dataclass

from nosolear.domain.observations import Observation


@dataclass(frozen=True, slots=True)
class StoredObservation:
    """A stored observation with its row id, so feedback can point back at its evidence."""

    id: int
    observation: Observation
