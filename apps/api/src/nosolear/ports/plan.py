"""Ports for the daily plan: the re-check schedule of mastered keys. Adapters: `persistence`."""

from collections.abc import Mapping
from typing import Protocol

from nosolear.domain.rechecks import RecheckState


class RecheckStore(Protocol):
    def load(self) -> dict[str, RecheckState]: ...

    def save(self, states: Mapping[str, RecheckState]) -> None: ...
