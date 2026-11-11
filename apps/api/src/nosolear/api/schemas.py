from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ProfileEntryOut(BaseModel):
    error_key: str
    skill: Literal["sounds", "on_the_spot", "articulate"]
    family: str
    description: str
    impact: int
    p_hat: float
    ci_low: float
    ci_high: float
    n_eff: float
    status: Literal["unknown", "active", "improving", "watching", "mastered"]
    priority: float
    last_seen_at: datetime


class ProfileOut(BaseModel):
    as_of: datetime | None
    taxonomy_version: int
    algo_version: int
    entries: list[ProfileEntryOut]
