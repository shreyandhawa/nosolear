"""Ports for the daily plan: the re-check schedule, the stored plans and their inputs.

Adapters: `persistence`.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from nosolear.domain.daily_plan import DailyPlan, PromptCandidate
from nosolear.domain.profile import Profile
from nosolear.domain.rechecks import RecheckState
from nosolear.domain.taxonomy import Skill


class RecheckStore(Protocol):
    def load(self) -> dict[str, RecheckState]: ...

    def save(self, states: Mapping[str, RecheckState]) -> None: ...


class ProfileReader(Protocol):
    def latest(self) -> Profile | None: ...


class PromptBank(Protocol):
    def prompts(self) -> list[PromptCandidate]: ...


class ScoredKeys(Protocol):
    def is_scored(self, error_key: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class StoredPlan:
    id: str
    plan: DailyPlan


class DailyPlanStore(Protocol):
    def get(self, for_date: date) -> StoredPlan | None: ...

    def add(self, plan: DailyPlan) -> StoredPlan:
        """Stores the plan, or returns the one already stored for its date."""
        ...

    def recent_focus_keys(self, before: date, limit: int = 3) -> dict[Skill, list[str]]: ...

    def recent_prompt_ids(self, before: date, limit: int = 3) -> list[str]: ...
