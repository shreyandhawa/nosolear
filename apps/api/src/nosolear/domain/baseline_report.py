"""The baseline report: the keys this session missed, ranked, with clips and honest notes. Pure.

Clips come only from the session's own misses. Notes say what the scores can't yet promise, and
each appears only when it applies.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from nosolear.domain.observations import Observation, Outcome
from nosolear.domain.profile import Profile, ProfileEntry
from nosolear.domain.skill_scores import SkillScore
from nosolear.domain.status import Status
from nosolear.domain.taxonomy import Skill


class CalibrationState(StrEnum):
    NOT_RUN = "not_run"
    SKIPPED = "skipped"
    CALIBRATED = "calibrated"


@dataclass(frozen=True, slots=True)
class ClipRef:
    attempt_id: str
    start_ms: int
    end_ms: int
    word: str | None
    expected: str | None
    produced: str | None


@dataclass(frozen=True, slots=True)
class ReportItem:
    error_key: str
    description: str
    skill: Skill
    impact: int
    p_hat: float
    ci_low: float
    ci_high: float
    n_eff: float
    status: Status
    priority: float
    provisional: bool
    clips: tuple[ClipRef, ...]


@dataclass(frozen=True, slots=True)
class BaselineReport:
    session_id: str
    completed_at: datetime
    calibration: CalibrationState
    scoring_config_id: str
    snapshot_id: str
    items: tuple[ReportItem, ...]
    skill_scores: tuple[SkillScore, ...]
    notes: tuple[str, ...]


NOTE_SKIPPED = "Calibration was skipped: sound and prosody scores are provisional."
NOTE_NOT_RUN = "Calibration hasn't been run: sound and prosody scores are provisional."
NOTE_FILLERS = "Fillers may be undercounted: this transcriber drops filler words."
NOTE_NO_COACH = "The coach was unavailable: grammar, structure and clarity were not scored."


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _clip(obs: Observation) -> ClipRef | None:
    if obs.attempt_id is None:
        return None
    start = _int(obs.evidence.get("start_ms"))
    end = _int(obs.evidence.get("end_ms"))
    if start is None or end is None:
        return None
    return ClipRef(
        attempt_id=obs.attempt_id,
        start_ms=start,
        end_ms=end,
        word=_text(obs.evidence.get("word")),
        expected=_text(obs.evidence.get("expected")),
        produced=_text(obs.evidence.get("produced")),
    )


def _clips(
    key: str, session_observations: Sequence[Observation], max_clips: int
) -> tuple[ClipRef, ...]:
    misses = sorted(
        (o for o in session_observations if o.error_key == key and o.outcome is Outcome.MISS),
        key=lambda o: (o.observed_at, _int(o.evidence.get("start_ms")) or 0),
    )
    clips = [clip for clip in (_clip(o) for o in misses) if clip is not None]
    return tuple(clips[:max_clips])


def _item(
    entry: ProfileEntry, session_observations: Sequence[Observation], max_clips: int
) -> ReportItem:
    defn = entry.definition
    return ReportItem(
        error_key=defn.key,
        description=defn.description,
        skill=defn.skill,
        impact=defn.impact,
        p_hat=entry.estimate.p_hat,
        ci_low=entry.estimate.ci_low,
        ci_high=entry.estimate.ci_high,
        n_eff=entry.estimate.n_eff,
        status=entry.status,
        priority=entry.priority,
        provisional=entry.provisional,
        clips=_clips(defn.key, session_observations, max_clips),
    )


def _notes(
    calibration: CalibrationState, *, fillers_undercounted: bool, coach_scored: bool
) -> tuple[str, ...]:
    notes: list[str] = []
    if calibration is CalibrationState.SKIPPED:
        notes.append(NOTE_SKIPPED)
    elif calibration is CalibrationState.NOT_RUN:
        notes.append(NOTE_NOT_RUN)
    if fillers_undercounted:
        notes.append(NOTE_FILLERS)
    if not coach_scored:
        notes.append(NOTE_NO_COACH)
    return tuple(notes)


def build_baseline_report(
    *,
    session_id: str,
    completed_at: datetime,
    profile: Profile,
    session_observations: Sequence[Observation],
    skill_scores: Sequence[SkillScore],
    calibration: CalibrationState,
    scoring_config_id: str,
    snapshot_id: str,
    fillers_undercounted: bool,
    coach_scored: bool,
    max_clips: int = 3,
) -> BaselineReport:
    missed = {o.error_key for o in session_observations if o.outcome is Outcome.MISS}
    entries = sorted(
        (e for e in profile.entries if e.definition.key in missed),
        key=lambda e: (-e.priority, e.definition.key),
    )
    return BaselineReport(
        session_id=session_id,
        completed_at=completed_at,
        calibration=calibration,
        scoring_config_id=scoring_config_id,
        snapshot_id=snapshot_id,
        items=tuple(_item(e, session_observations, max_clips) for e in entries),
        skill_scores=tuple(skill_scores),
        notes=_notes(
            calibration,
            fillers_undercounted=fillers_undercounted,
            coach_scored=coach_scored,
        ),
    )
