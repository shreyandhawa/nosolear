"""Response bodies of the calibration routes (ARCHITECTURE.md section 9.2)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CalibrationItemOut(BaseModel):
    attempt_id: str
    order: int
    error_key: str
    word: str
    deliberate: bool
    take: int
    instruction: str
    stand_in_text: str
    recorded: bool
    job_status: str | None


class CalibrationResultOut(BaseModel):
    detector: str
    error_key: str
    errors: int
    hits: int
    controls: int
    false_alarms: int
    correct_takes: int
    correct_flags: int
    covered: bool
    enabled: bool
    hit_rate: float | None
    false_alarm_rate: float | None
    correct_take_flag_rate: float | None
    warning: str | None


class CalibrationRunOut(BaseModel):
    run_id: str
    session_id: str | None
    status: Literal["running", "done", "skipped"]
    scoring_config_id: str | None
    started_at: datetime
    completed_at: datetime | None
    items: list[CalibrationItemOut]
    results: list[CalibrationResultOut]
