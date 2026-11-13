from datetime import date, datetime
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
    provisional: bool = False


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
    kind: Literal["analyze", "rescore", "calibrate"]
    attempt_id: str | None
    status: Literal["queued", "running", "done", "failed"]
    step: str | None
    progress: float
    tries: int
    steps: list[StepOut]


class ErrorOut(BaseModel):
    code: str
    message: str


class UploadAcceptedOut(BaseModel):
    recording_id: str
    job_id: str
    duration_ms: int


class JobAcceptedOut(BaseModel):
    job_id: str


SkillName = Literal["sounds", "on_the_spot", "articulate"]
FocusStatus = Literal["unknown", "active", "improving", "watching", "mastered"]


class FocusOut(BaseModel):
    """A focus without its sampled score: the sampled rate and the score stay server-side."""

    skill: SkillName
    error_key: str
    description: str
    impact: int
    status: FocusStatus
    p_hat: float
    provisional: bool
    source: Literal["profile", "fallback"]


class ProbeOut(BaseModel):
    skill: SkillName
    error_key: str
    due_at: datetime


class PromptOut(BaseModel):
    id: str
    text: str
    target_keys: list[str]


class DrillOut(BaseModel):
    skill: SkillName
    error_key: str
    drill_family: str


class PlanStepOut(BaseModel):
    kind: Literal["speak", "analyze", "feedback", "drill", "log"]
    skill: SkillName | None
    duration_s: int


class PlanOut(BaseModel):
    id: str
    for_date: date
    seed: int
    protocol_version: int
    foci: list[FocusOut]
    probe: ProbeOut | None
    prompt: PromptOut | None
    drills: list[DrillOut]
    steps: list[PlanStepOut]


class AttemptOut(BaseModel):
    id: str
    step: str
    prompt_text: str | None


class DailySessionOut(BaseModel):
    session_id: str
    plan_id: str
    attempts: list[AttemptOut]


FeedbackSourceName = Literal["coach", "template"]
FeedbackStateName = Literal["fix", "clean", "not_scored"]
FallbackReasonName = Literal[
    "cap_exceeded", "provider_unavailable", "capability_missing", "invalid_output"
]


class FeedbackItemOut(BaseModel):
    """One card's text. `source` says whether the coach wrote it or a template did, and a template
    carries the reason the coach was not used."""

    id: str
    error_key: str
    message: str
    model_text: str | None
    source: FeedbackSourceName
    fallback_reason: FallbackReasonName | None
    attempt_id: str | None
    start_ms: int | None
    end_ms: int | None
    word: str | None


class SkillFeedbackOut(BaseModel):
    """`clean` means the skill was scored with no miss; `not_scored` means it was not scored today.
    Neither has a card."""

    skill: SkillName
    state: FeedbackStateName
    item: FeedbackItemOut | None


class FeedbackOut(BaseModel):
    session_id: str
    degraded: bool
    skills: list[SkillFeedbackOut]


class CompleteOut(BaseModel):
    session_id: str
    completed_at: datetime
    already_completed: bool
