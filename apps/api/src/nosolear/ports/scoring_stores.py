"""Ports for scoring configs and extraction markers. Adapters live in `persistence`."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol

from nosolear.domain.analyses import StoredAnalysis
from nosolear.domain.extraction.extract import ExtractionItem
from nosolear.domain.observations import Observation
from nosolear.domain.scoring import ScoringConfig
from nosolear.domain.taxonomy import Detector


class ScoringConfigReader(Protocol):
    def newest(self) -> ScoringConfig: ...

    def get(self, config_id: str) -> ScoringConfig: ...


class ScoringConfigWriter(Protocol):
    def add(
        self, config: ScoringConfig, *, capabilities: Mapping[str, object], created_at: datetime
    ) -> None: ...


class ExtractionWriter(Protocol):
    def write(
        self,
        *,
        attempt_id: str,
        scoring_config_id: str,
        detector: Detector,
        observations: Sequence[Observation],
        created_at: datetime,
    ) -> bool: ...


class ExtractionInputs(Protocol):
    """What the extract use cases read: an attempt's item, its stored analyses, and the attempts
    a re-score covers."""

    def item(self, attempt_id: str) -> ExtractionItem | None: ...

    def analyses(self, attempt_id: str) -> list[StoredAnalysis]: ...

    def rescorable_attempt_ids(self) -> list[str]: ...
