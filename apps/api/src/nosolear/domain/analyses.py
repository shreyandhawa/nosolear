"""Stored analyses: one provider result per attempt and kind. Pure: no I/O."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class AnalysisKind(StrEnum):
    PRONUNCIATION = "pronunciation"
    TRANSCRIPT = "transcript"
    PHONE_PROBE = "phone_probe"
    COACH = "coach"


@dataclass(frozen=True, slots=True)
class NewAnalysis:
    attempt_id: str
    kind: AnalysisKind
    provider: str
    provider_version: str
    adapter: str
    adapter_version: int
    raw: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class StoredAnalysis:
    id: int
    attempt_id: str
    kind: AnalysisKind
    provider: str
    provider_version: str
    adapter: str
    adapter_version: int
    raw: Mapping[str, object]
    created_at: datetime
