"""Response bodies of the baseline routes (ARCHITECTURE.md section 9.1)."""

from datetime import datetime

from pydantic import BaseModel


class BaselineItemOut(BaseModel):
    attempt_id: str
    order: int
    section: str
    step: str
    text: str
    scripted: bool
    max_seconds: int | None
    start_limit_seconds: int | None
    stand_in_text: str
    recorded: bool
    job_status: str | None


class BaselineSessionOut(BaseModel):
    session_id: str
    protocol_version: int
    started_at: datetime
    completed_at: datetime | None
    items: list[BaselineItemOut]


class ClipOut(BaseModel):
    attempt_id: str
    start_ms: int
    end_ms: int
    word: str | None
    expected: str | None
    produced: str | None


class ReportItemOut(BaseModel):
    error_key: str
    description: str
    skill: str
    impact: int
    p_hat: float
    ci_low: float
    ci_high: float
    n_eff: float
    status: str
    priority: float
    provisional: bool
    clips: list[ClipOut]


class SkillScoreOut(BaseModel):
    skill: str
    score: float
    values: dict[str, float]
    scores: dict[str, float]


class BaselineReportOut(BaseModel):
    session_id: str
    completed_at: datetime
    calibration: str
    scoring_config_id: str
    snapshot_id: str
    items: list[ReportItemOut]
    skill_scores: list[SkillScoreOut]
    notes: list[str]
