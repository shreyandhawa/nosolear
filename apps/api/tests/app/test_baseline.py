"""The baseline session's use cases: start, complete, the report and the rescore refresh."""

from collections.abc import Callable
from typing import Any

import pytest
from baseline_fixtures import small_baseline_content
from factories import PACK, TAX
from harness import Harness
from sqlalchemy import text

from nosolear.app.baseline import (
    BaselineNotOpen,
    BaselinePending,
    baseline_report,
    baseline_view,
    complete_baseline,
    start_baseline,
)
from nosolear.app.calibrate import finish_calibration, start_calibration
from nosolear.domain.baseline_report import BaselineReport, CalibrationState
from nosolear.domain.coach import Rubric
from nosolear.domain.content import SeedContent
from nosolear.domain.skill_scores import SkillScore
from nosolear.domain.taxonomy import Detector, Skill
from nosolear.persistence.baseline_repository import BaselineRepository
from nosolear.persistence.calibration_repository import CalibrationRepository
from nosolear.persistence.repositories import ObservationRepository, ProfileRepository
from nosolear.persistence.scoring_repository import (
    ExtractionInputsRepository,
    ScoringConfigRepository,
)

AZURE = frozenset({Detector.AZURE_PA})
VW = "sound.sub.v.w"
NOTE_NOT_RUN = "Calibration hasn't been run: sound and prosody scores are provisional."


def _store(h: Harness) -> BaselineRepository:
    return BaselineRepository(h.engine)


def _content() -> SeedContent:
    return small_baseline_content()


def _start(h: Harness):
    return start_baseline(store=_store(h), content=_content(), clock=h.clock)


def _record_all(h: Harness, view: Any, *, drain: bool = True) -> None:
    for item in view.items:
        h.upload(item.attempt_id, item.stand_in_text)
    if drain:
        h.drain()


def _complete(h: Harness) -> BaselineReport:
    return complete_baseline(
        store=_store(h),
        content=_content(),
        inputs=ExtractionInputsRepository(h.engine),
        observations=ObservationRepository(h.engine),
        profiles=ProfileRepository(h.engine, TAX),
        configs=ScoringConfigRepository(h.engine, TAX),
        calibration=CalibrationRepository(h.engine, h.clock),
        taxonomy=TAX,
        pack=PACK,
        clock=h.clock,
    )


def _report(h: Harness) -> BaselineReport | None:
    return baseline_report(
        store=_store(h),
        observations=ObservationRepository(h.engine),
        profiles=ProfileRepository(h.engine, TAX),
        configs=ScoringConfigRepository(h.engine, TAX),
        calibration=CalibrationRepository(h.engine, h.clock),
        inputs=ExtractionInputsRepository(h.engine),
    )


def _calibrate(h: Harness) -> None:
    # The oracle's user errors apply to every word, correct takes included, so a calibration of
    # the same voice would flag its own correct takes. The calibration uses a clean voice.
    h.voice.user_errors.clear()
    store = CalibrationRepository(h.engine, h.clock)
    services: Any = h.client.app.state.services  # pyright: ignore[reportAttributeAccessIssue]
    view = start_calibration(
        store=store,
        content=_content(),
        pack=PACK,
        available=AZURE,
        taxonomy=TAX,
        clock=h.clock,
    )
    for item in view.items:
        h.upload(item.attempt_id, item.stand_in_text)
    h.drain()
    finish_calibration(store=store, queue=services.jobs)
    h.drain()


def _entry(report: BaselineReport, key: str):
    return next(i for i in report.items if i.error_key == key)


def test_start_creates_protocol_attempts_in_order(make_harness: Callable[..., Harness]):
    h = make_harness(content=_content())
    view = _start(h)
    assert [i.section for i in view.items] == [
        "read_aloud",
        "read_aloud",
        "word_list",
        "free_talk",
        "rapid_questions",
        "articulate",
    ]
    assert [i.scripted for i in view.items] == [True, True, True, False, False, False]
    assert view.items[0].stand_in_text == "Seven vans came."
    assert view.items[3].stand_in_text == "Tell me about your day."
    assert view.items[4].start_limit_seconds == 5
    assert view.items[5].max_seconds == 60


def test_start_returns_the_open_session(make_harness: Callable[..., Harness]):
    h = make_harness(content=_content())
    first = _start(h)
    second = _start(h)
    assert first.session.id == second.session.id
    assert len(second.items) == len(first.items)


def test_view_is_none_before_any_session(make_harness: Callable[..., Harness]):
    h = make_harness(content=_content())
    assert baseline_view(store=_store(h), content=_content()) is None


def test_complete_without_an_open_session_is_refused(make_harness: Callable[..., Harness]):
    h = make_harness(content=_content())
    with pytest.raises(BaselineNotOpen):
        _complete(h)


def test_complete_requires_every_item_settled(make_harness: Callable[..., Harness]):
    h = make_harness(content=_content())
    view = _start(h)
    _record_all(h, view, drain=False)
    with pytest.raises(BaselinePending):
        _complete(h)


def test_complete_writes_snapshot_scores_and_report(make_harness: Callable[..., Harness]):
    h = make_harness(content=_content(), rubric=Rubric(structure=3, clarity=3, concision=3))
    h.voice.user_errors["v"] = "w"
    view = _start(h)
    _record_all(h, view)
    report = _complete(h)

    top = report.items[0]
    assert top.error_key == VW and top.provisional
    attempts = {i.attempt_id for i in view.items}
    assert top.clips and all(c.attempt_id in attempts for c in top.clips)
    assert {s.skill for s in report.skill_scores} == {
        Skill.SOUNDS,
        Skill.ON_THE_SPOT,
        Skill.ARTICULATE,
    }
    assert NOTE_NOT_RUN in report.notes
    with h.engine.connect() as conn:
        rows = conn.execute(text("SELECT reason, session_id FROM profile_snapshots")).all()
    assert [(r.reason, r.session_id) for r in rows] == [("baseline", report.session_id)]
    view_after = baseline_view(store=_store(h), content=_content())
    assert view_after is not None and view_after.session.completed_at is not None


def test_report_is_none_before_completion(make_harness: Callable[..., Harness]):
    h = make_harness(content=_content())
    _start(h)
    assert _report(h) is None


def test_report_reads_the_completed_baseline(make_harness: Callable[..., Harness]):
    h = make_harness(content=_content(), rubric=Rubric(structure=3, clarity=3, concision=3))
    h.voice.user_errors["v"] = "w"
    _record_all(h, _start(h))
    completed = _complete(h)
    again = _report(h)
    assert again is not None
    assert again.session_id == completed.session_id
    assert again.snapshot_id == completed.snapshot_id
    assert [i.error_key for i in again.items] == [i.error_key for i in completed.items]


def test_rescore_refreshes_completed_baseline_report(make_harness: Callable[..., Harness]):
    h = make_harness(content=_content(), rubric=Rubric(structure=3, clarity=3, concision=3))
    h.voice.user_errors["v"] = "w"
    _record_all(h, _start(h))
    before = _complete(h)
    assert _entry(before, VW).provisional is True

    _calibrate(h)

    after = _report(h)
    assert after is not None
    assert _entry(after, VW).provisional is False
    assert after.snapshot_id != before.snapshot_id
    assert after.calibration is CalibrationState.CALIBRATED


def test_baseline_scores_are_stored_for_the_session(make_harness: Callable[..., Harness]):
    h = make_harness(content=_content(), rubric=Rubric(structure=3, clarity=3, concision=3))
    _record_all(h, _start(h))
    report = _complete(h)
    stored: tuple[SkillScore, ...] = _store(h).scores(report.session_id)
    assert {s.skill for s in stored} == {s.skill for s in report.skill_scores}
