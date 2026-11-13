"""The analysis store port. Adapters live in `persistence`."""

from typing import Protocol

from nosolear.domain.analyses import AnalysisKind, NewAnalysis, StoredAnalysis


class AnalysisStore(Protocol):
    def get(self, attempt_id: str, kind: AnalysisKind) -> StoredAnalysis | None: ...

    def put(self, analysis: NewAnalysis) -> StoredAnalysis:
        """Idempotent: returns the stored row for (attempt_id, kind), never overwriting it."""
        ...

    def for_attempt(self, attempt_id: str) -> list[StoredAnalysis]: ...
