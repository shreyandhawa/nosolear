"""The extract step of an analyze job, and `extract_attempt` on its own."""

import json

from factories import PACK, TAX, count
from harness import Harness
from sqlalchemy import text

from nosolear.app.extract_attempt import extract_attempt
from nosolear.domain.analyses import AnalysisKind
from nosolear.domain.observations import Outcome
from nosolear.persistence.scoring_repository import (
    ExtractionInputsRepository,
    ExtractionRepository,
    ScoringConfigRepository,
)


def _extract(h: Harness, attempt_id: str):
    return extract_attempt(
        attempt_id=attempt_id,
        inputs=ExtractionInputsRepository(h.engine),
        configs=ScoringConfigRepository(h.engine, TAX),
        extractions=ExtractionRepository(h.engine),
        pack=PACK,
        taxonomy=TAX,
        clock=h.clock,
    )


def test_extract_step_stamps_v0_and_provisional(harness: Harness) -> None:
    a = harness.attempt(step="read_aloud", scripted=True, reference_text="Seven vans.")
    harness.voice.user_errors["v"] = "w"
    harness.upload(a, "Seven vans.")
    harness.drain()
    obs = [o for o in harness.observations() if o.error_key == "sound.sub.v.w"]
    assert obs and all(
        o.scoring_config_id == "v0" and o.provisional and o.outcome is Outcome.MISS for o in obs
    )


def test_resumed_job_does_not_double_count(harness: Harness) -> None:
    a = harness.attempt(step="read_aloud", scripted=True, reference_text="Seven vans.")
    harness.voice.user_errors["v"] = "w"
    harness.upload(a, "Seven vans.")
    harness.drain()
    before = len(harness.observations())
    again = _extract(harness, a)
    assert again.written == 0
    assert len(harness.observations()) == before


def test_calibration_attempts_write_no_observations(harness: Harness) -> None:
    a = harness.attempt(step="calibration", scripted=True, reference_text="Seven vans.")
    harness.upload(a, "Seven vans.")
    harness.drain()
    assert harness.observations() == []
    assert count(harness.engine, "extractions") == 0


def test_probe_skipped_under_v0_and_run_for_calibration(make_harness) -> None:
    h = make_harness(probe=True)
    baseline = h.attempt(step="read_aloud", scripted=True, reference_text="Seven vans.")
    h.upload(baseline, "Seven vans.")
    h.drain()
    assert h.voice.calls["probe"] == 0
    calibration = h.attempt(step="calibration", scripted=True, reference_text="Seven vans.")
    h.upload(calibration, "Seven vans.")
    h.drain()
    assert h.voice.calls["probe"] == 1


def test_transcriber_and_coach_skip_calibration(harness: Harness) -> None:
    a = harness.attempt(step="calibration", scripted=True, reference_text="Seven vans.")
    harness.upload(a, "Seven vans.")
    harness.drain()
    assert harness.voice.calls["transcriber"] == 0
    kinds = {stored.kind for stored in ExtractionInputsRepository(harness.engine).analyses(a)}
    assert kinds == {AnalysisKind.PRONUNCIATION}


def test_undecodable_analysis_is_skipped_not_fatal(harness: Harness) -> None:
    a = harness.attempt(step="read_aloud", scripted=True, reference_text="Seven vans.")
    harness.voice.user_errors["v"] = "w"
    harness.upload(a, "Seven vans.")
    harness.drain()
    with harness.engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE analyses SET raw_json = :raw "
                "WHERE attempt_id = :a AND kind = 'pronunciation'"
            ),
            {"raw": json.dumps({"mode": 3}), "a": a},
        )
    summary = _extract(harness, a)
    assert summary.undecodable == ("pronunciation",)


def test_extract_rebuilds_profile_without_snapshot(harness: Harness) -> None:
    before = count(harness.engine, "profile_snapshots")
    a = harness.attempt(step="read_aloud", scripted=True, reference_text="Seven vans.")
    harness.voice.user_errors["v"] = "w"
    harness.upload(a, "Seven vans.")
    harness.drain()
    assert count(harness.engine, "profile_entries") > 0
    assert count(harness.engine, "profile_snapshots") == before
