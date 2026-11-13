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


class ReadinessRowOut(BaseModel):
    component: Literal[
        "azure_speech",
        "azure_capabilities",
        "anthropic",
        "transcriber",
        "phone_probe",
        "language_pack",
        "data_dir",
        "usage",
    ]
    label: str
    status: Literal["ready", "missing", "not_installed", "not_probed", "degraded"]
    reason: str
    fix: str | None


class ReadinessOut(BaseModel):
    ready: bool
    rows: list[ReadinessRowOut]


class StepOut(BaseModel):
    name: str
    state: Literal["pending", "running", "done", "skipped", "failed", "blocked"]
    error_code: str | None
    message: str | None


class JobOut(BaseModel):
    id: str
    kind: Literal["analyze", "rescore"]
    attempt_id: str | None
    status: Literal["queued", "running", "done", "failed"]
    step: str | None
    progress: float
    tries: int
    steps: list[StepOut]


class ErrorOut(BaseModel):
    code: str
    message: str
