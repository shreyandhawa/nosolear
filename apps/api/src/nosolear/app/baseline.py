"""The baseline session's use cases (ARCHITECTURE.md section 9.1). Each takes its ports as
arguments, so the routes and the CLI wire the same code. Nothing here calls a provider: a
completed baseline reads stored analyses and observations only."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from nosolear.app.extract_attempt import collect_results
from nosolear.app.rebuild_profile import rebuild_profile
from nosolear.domain.analyses import AnalysisKind
from nosolear.domain.baseline_report import (
    BaselineReport,
    CalibrationState,
    build_baseline_report,
)
from nosolear.domain.coach import Rubric
from nosolear.domain.content import BaselineItem, BaselineSection, SeedContent
from nosolear.domain.observations import Observation, Outcome
from nosolear.domain.packs import LanguagePack
from nosolear.domain.profile import build_profile
from nosolear.domain.results import parse_transcript
from nosolear.domain.scoring import ConfigKind
from nosolear.domain.skill_scores import SessionEvidence, skill_scores
from nosolear.domain.speech import PronunciationAssessment, Transcript, raw_result_of
from nosolear.domain.taxonomy import Family, Taxonomy
from nosolear.ports.baseline_store import (
    BaselineItemRecord,
    BaselineProfileStore,
    BaselineSessionRecord,
    BaselineStore,
)
from nosolear.ports.calibration_store import CalibrationStore
from nosolear.ports.clock import Clock
from nosolear.ports.scoring_stores import ExtractionInputs, ScoringConfigReader
from nosolear.ports.stores import ObservationReader, ProfileWriter

BASELINE_REASON = "baseline"
SETTLED_JOB_STATUSES = frozenset({"done", "failed"})
SOUND_FAMILIES = frozenset({Family.SUB, Family.LOW, Family.INS, Family.DEL})
UNSCRIPTED_STEPS = frozenset({"speak", "quick_answer", "articulate"})


class BaselineError(ValueError):
    """A refused step. `message` is a literal sentence the API and the CLI may show."""

    code: str = "baseline_error"
    message: str = "The baseline step was refused."

    def __init__(self) -> None:
        super().__init__(self.message)


class BaselinePending(BaselineError):
    code = "baseline_pending"
    message = "Record every baseline item and wait for its analysis to finish before completing."


class BaselineNotOpen(BaselineError):
    code = "baseline_not_open"
    message = "No baseline is in progress."


@dataclass(frozen=True, slots=True)
class BaselineItemView:
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


@dataclass(frozen=True, slots=True)
class BaselineView:
    session: BaselineSessionRecord
    items: tuple[BaselineItemView, ...]


@dataclass(frozen=True, slots=True)
class _Found:
    section: BaselineSection
    item: BaselineItem


def _index(content: SeedContent) -> dict[str, _Found]:
    return {
        entry.item.id: _Found(section, entry)
        for section in content.protocol.sections
        for entry in section.items
    }


def _item_view(record: BaselineItemRecord, found: _Found | None) -> BaselineItemView:
    if found is None:
        return BaselineItemView(
            attempt_id=record.attempt_id,
            order=record.order,
            section=record.step,
            step=record.step,
            text="",
            scripted=record.scripted,
            max_seconds=None,
            start_limit_seconds=None,
            stand_in_text="",
            recorded=record.recorded,
            job_status=record.job_status,
        )
    text = found.item.item.text
    return BaselineItemView(
        attempt_id=record.attempt_id,
        order=record.order,
        section=found.section.name,
        step=record.step,
        text=text,
        scripted=record.scripted,
        max_seconds=found.section.max_seconds,
        start_limit_seconds=found.section.start_limit_seconds,
        stand_in_text=text if record.scripted else (found.item.stand_in or ""),
        recorded=record.recorded,
        job_status=record.job_status,
    )


def _view(
    store: BaselineStore, session: BaselineSessionRecord, content: SeedContent
) -> BaselineView:
    index = _index(content)
    items = tuple(
        _item_view(record, index.get(record.item_id)) for record in store.items(session.id)
    )
    return BaselineView(session=session, items=items)


def start_baseline(*, store: BaselineStore, content: SeedContent, clock: Clock) -> BaselineView:
    """Starts a baseline, or returns the one already open."""
    session = store.open_session()
    if session is None:
        store.create(session_id=uuid4().hex, protocol=content.protocol, now=clock.now())
        session = store.open_session()
        if session is None:
            raise RuntimeError("the baseline session was not written")
    return _view(store, session, content)


def baseline_view(*, store: BaselineStore, content: SeedContent) -> BaselineView | None:
    """The open baseline, else the latest completed one, else None."""
    session = store.open_session()
    if session is None:
        session = store.latest_completed()
    if session is None:
        return None
    return _view(store, session, content)


def _settled(items: Sequence[BaselineItemRecord]) -> bool:
    return all(item.recorded and item.job_status in SETTLED_JOB_STATUSES for item in items)


def _flags(items: Sequence[BaselineItemRecord], inputs: ExtractionInputs) -> tuple[bool, bool]:
    """(fillers_undercounted, coach_scored) for the session's stored analyses."""
    fillers_undercounted = False
    coach_scored = False
    for item in items:
        for stored in inputs.analyses(item.attempt_id):
            if stored.kind is AnalysisKind.COACH:
                coach_scored = True
            if stored.kind is AnalysisKind.TRANSCRIPT:
                transcript = parse_transcript(raw_result_of(stored))
                fillers_undercounted = fillers_undercounted or not transcript.fillers_kept
    return fillers_undercounted, coach_scored


def _evidence(
    items: Sequence[BaselineItemRecord],
    *,
    inputs: ExtractionInputs,
    observations: ObservationReader,
    taxonomy: Taxonomy,
) -> SessionEvidence:
    scripted_pronunciation: list[PronunciationAssessment] = []
    quick: list[Transcript] = []
    unscripted: list[Transcript] = []
    rubric: Rubric | None = None
    for item in items:
        results, _ = collect_results(
            inputs.analyses(item.attempt_id), step=item.step, taxonomy=taxonomy
        )
        if item.scripted and results.pronunciation is not None:
            scripted_pronunciation.append(results.pronunciation)
        if results.transcript is not None:
            if item.step == "quick_answer":
                quick.append(results.transcript)
            if item.step in UNSCRIPTED_STEPS:
                unscripted.append(results.transcript)
        if item.step == "articulate" and results.coach is not None:
            rubric = results.coach.rubric
    session_ids = {item.attempt_id for item in items}
    current = [o for o in observations.current() if o.attempt_id in session_ids]
    return SessionEvidence(
        scripted_pronunciation=tuple(scripted_pronunciation),
        sound_observations=tuple(
            o for o in current if taxonomy.get(o.error_key).family in SOUND_FAMILIES
        ),
        quick_answers=tuple(quick),
        unscripted=tuple(unscripted),
        grammar_misses=_grammar_misses(current, taxonomy),
        articulate_rubric=rubric,
    )


def _grammar_misses(observations: Sequence[Observation], taxonomy: Taxonomy) -> int:
    return sum(
        1
        for o in observations
        if o.outcome is Outcome.MISS and taxonomy.get(o.error_key).family is Family.GRAMMAR
    )


def _save_scores(
    store: BaselineStore,
    session_id: str,
    *,
    inputs: ExtractionInputs,
    observations: ObservationReader,
    taxonomy: Taxonomy,
) -> None:
    items = store.items(session_id)
    evidence = _evidence(items, inputs=inputs, observations=observations, taxonomy=taxonomy)
    store.save_scores(session_id, skill_scores(evidence))


def _calibration_state(
    configs: ScoringConfigReader, calibration: CalibrationStore
) -> CalibrationState:
    if configs.newest().kind is ConfigKind.CALIBRATED:
        return CalibrationState.CALIBRATED
    latest = calibration.latest()
    if latest is not None and latest.status == "skipped":
        return CalibrationState.SKIPPED
    return CalibrationState.NOT_RUN


def _report(
    session_id: str,
    completed_at: datetime,
    *,
    store: BaselineStore,
    observations: ObservationReader,
    profiles: BaselineProfileStore,
    configs: ScoringConfigReader,
    calibration: CalibrationStore,
    inputs: ExtractionInputs,
) -> BaselineReport | None:
    found = profiles.latest_snapshot(session_id, BASELINE_REASON)
    if found is None:
        return None
    snapshot_id, profile = found
    items = store.items(session_id)
    session_ids = {item.attempt_id for item in items}
    session_observations = [o for o in observations.current() if o.attempt_id in session_ids]
    fillers_undercounted, coach_scored = _flags(items, inputs)
    config = configs.newest()
    return build_baseline_report(
        session_id=session_id,
        completed_at=completed_at,
        profile=profile,
        session_observations=session_observations,
        skill_scores=store.scores(session_id),
        calibration=_calibration_state(configs, calibration),
        scoring_config_id=config.id,
        snapshot_id=snapshot_id,
        fillers_undercounted=fillers_undercounted,
        coach_scored=coach_scored,
    )


def complete_baseline(
    *,
    store: BaselineStore,
    content: SeedContent,
    inputs: ExtractionInputs,
    observations: ObservationReader,
    profiles: BaselineProfileStore,
    configs: ScoringConfigReader,
    calibration: CalibrationStore,
    taxonomy: Taxonomy,
    pack: LanguagePack,
    clock: Clock,
) -> BaselineReport:
    """Snapshots the profile under this session, stores its scores, and closes the session."""
    session = store.open_session()
    if session is None:
        raise BaselineNotOpen()
    if not _settled(store.items(session.id)):
        raise BaselinePending()
    now = clock.now()
    rebuild_profile(
        observations=observations,
        profiles=profiles,
        taxonomy=taxonomy,
        pack=pack,
        clock=clock,
        session_id=session.id,
        reason=BASELINE_REASON,
    )
    _save_scores(store, session.id, inputs=inputs, observations=observations, taxonomy=taxonomy)
    store.complete(session.id, completed_at=now)
    report = _report(
        session.id,
        now,
        store=store,
        observations=observations,
        profiles=profiles,
        configs=configs,
        calibration=calibration,
        inputs=inputs,
    )
    if report is None:
        raise RuntimeError("the baseline snapshot was not written")
    return report


def refresh_baseline(
    session_id: str,
    *,
    store: BaselineStore,
    inputs: ExtractionInputs,
    observations: ObservationReader,
    profiles: ProfileWriter,
    taxonomy: Taxonomy,
    pack: LanguagePack,
) -> None:
    """Re-snapshots a completed baseline's profile from the current observations, as of its
    completion, and recomputes its scores. Calls no provider."""
    session = next((s for s in store.completed_sessions() if s.id == session_id), None)
    if session is None or session.completed_at is None:
        raise ValueError("refresh_baseline needs a completed session")
    profile = build_profile(
        observations.current(),
        as_of=session.completed_at,
        taxonomy=taxonomy,
        pack=pack,
    )
    profiles.snapshot(profile, session_id=session_id, reason=BASELINE_REASON)
    _save_scores(store, session_id, inputs=inputs, observations=observations, taxonomy=taxonomy)


def refresh_completed_baselines(
    *,
    store: BaselineStore,
    inputs: ExtractionInputs,
    observations: ObservationReader,
    profiles: ProfileWriter,
    taxonomy: Taxonomy,
    pack: LanguagePack,
) -> int:
    """Refreshes every completed baseline. Returns how many it refreshed."""
    sessions = store.completed_sessions()
    for session in sessions:
        refresh_baseline(
            session.id,
            store=store,
            inputs=inputs,
            observations=observations,
            profiles=profiles,
            taxonomy=taxonomy,
            pack=pack,
        )
    return len(sessions)


def baseline_report(
    *,
    store: BaselineStore,
    observations: ObservationReader,
    profiles: BaselineProfileStore,
    configs: ScoringConfigReader,
    calibration: CalibrationStore,
    inputs: ExtractionInputs,
) -> BaselineReport | None:
    """The report of the latest completed baseline, or None when none is completed."""
    session = store.latest_completed()
    if session is None or session.completed_at is None:
        return None
    return _report(
        session.id,
        session.completed_at,
        store=store,
        observations=observations,
        profiles=profiles,
        configs=configs,
        calibration=calibration,
        inputs=inputs,
    )
