"""The calibration store port: runs, their session attempts, trials and control rows.
Adapters live in `persistence`."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from nosolear.domain.analyses import AnalysisKind
from nosolear.domain.calibration import CalibrationPlan, Trial
from nosolear.domain.scoring import ScoringConfig
from nosolear.domain.speech import RawResult
from nosolear.domain.taxonomy import Detector

RunStatus = Literal["running", "done", "skipped"]


class RunAlreadyOpen(ValueError):
    """A calibration run is still running; a second one is refused."""


@dataclass(frozen=True, slots=True)
class CalibrationRunRecord:
    id: str
    session_id: str | None
    status: RunStatus
    scoring_config_id: str | None
    started_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class CalibrationItemRecord:
    attempt_id: str
    order: int
    item_id: str
    error_key: str
    word: str
    deliberate: bool
    take: int
    recorded: bool
    job_status: str | None


@dataclass(frozen=True, slots=True)
class TrialRecord:
    id: int
    trial: Trial


class CalibrationStore(Protocol):
    def running(self) -> CalibrationRunRecord | None: ...

    def latest(self) -> CalibrationRunRecord | None: ...

    def start(
        self, *, run_id: str, session_id: str, plan: CalibrationPlan, now: datetime
    ) -> CalibrationRunRecord: ...

    def skip(self, *, run_id: str, now: datetime) -> CalibrationRunRecord: ...

    def items(self, run_id: str) -> list[CalibrationItemRecord]: ...

    def trials(self, run_id: str) -> list[TrialRecord]: ...

    def control_words(self, run_id: str) -> dict[str, str]:
        """The TTS hash of each control clip in this run, mapped to the word it says."""
        ...

    def control_analysis(
        self, tts_hash: str, run_id: str, kind: AnalysisKind
    ) -> RawResult | None: ...

    def add_control_analysis(
        self, tts_hash: str, run_id: str, kind: AnalysisKind, raw: RawResult
    ) -> None: ...

    def add_control_trials(
        self, run_id: str, tts_hash: str, pairs: Sequence[tuple[str, Detector]]
    ) -> None: ...

    def set_flags(self, flags: Mapping[int, bool | None]) -> None: ...

    def complete(
        self,
        *,
        run_id: str,
        config: ScoringConfig,
        capabilities: Mapping[str, object],
        now: datetime,
    ) -> None: ...

    def open_calibrate_job(self) -> str | None: ...
