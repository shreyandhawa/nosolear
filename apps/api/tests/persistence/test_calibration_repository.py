"""The calibration repository: runs, sessions, attempts, trials and control rows."""

from datetime import UTC, datetime

import pytest
from calibration_fixtures import SMALL_SET, small_content
from factories import T0, FixedClock, count

from nosolear.domain.analyses import AnalysisKind
from nosolear.domain.calibration import build_calibrated_config, plan_calibration
from nosolear.domain.content import seed_items
from nosolear.domain.jobs import JobKind
from nosolear.domain.scoring import ConfigKind
from nosolear.domain.speech import RawResult, SynthesizedClip
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as TAX
from nosolear.domain.taxonomy import Detector
from nosolear.persistence.calibration_repository import CalibrationRepository
from nosolear.persistence.content_repository import ContentRepository
from nosolear.persistence.job_queue import SqliteJobQueue
from nosolear.persistence.scoring_repository import ScoringConfigRepository
from nosolear.persistence.tts_cache import TtsCacheRepository
from nosolear.ports.calibration_store import RunAlreadyOpen

NOW = datetime(2026, 11, 13, tzinfo=UTC)
AZURE = frozenset({Detector.AZURE_PA})


@pytest.fixture
def store(db_engine):
    ContentRepository(db_engine).sync_seed(seed_items(small_content()), now=NOW)
    return CalibrationRepository(db_engine, FixedClock(NOW))


def plan():
    return plan_calibration(SMALL_SET, emphasis=[], available=AZURE, taxonomy=TAX)


def clip_row(db_engine) -> None:
    TtsCacheRepository(db_engine).put(
        SynthesizedClip(
            hash="abc",
            path="tts/abc.wav",
            voice="v",
            rate_percent=0,
            word_timings=(),
            duration_ms=1000,
        ),
        text="vest",
        created_at=NOW,
    )


def test_start_writes_session_attempts_trials_and_run(store, db_engine):
    run = store.start(run_id="r1", session_id="s1", plan=plan(), now=NOW)
    assert run.status == "running" and run.session_id == "s1"
    assert count(db_engine, "attempts") == 30
    assert count(db_engine, "calibration_trials") == 30
    assert store.running() == run
    items = store.items("r1")
    assert [i.order for i in items] == list(range(1, 31))
    assert sum(1 for i in items if i.deliberate) == 20


def test_a_second_open_run_is_refused(store):
    store.start(run_id="r1", session_id="s1", plan=plan(), now=NOW)
    with pytest.raises(RunAlreadyOpen):
        store.start(run_id="r2", session_id="s2", plan=plan(), now=NOW)


def test_skip_without_a_run_inserts_a_skipped_run(store):
    run = store.skip(run_id="r0", now=NOW)
    assert run.status == "skipped" and run.session_id is None
    assert store.running() is None


def test_skip_marks_the_open_run_skipped(store):
    store.start(run_id="r1", session_id="s1", plan=plan(), now=NOW)
    run = store.skip(run_id="r9", now=NOW)
    assert run.id == "r1" and run.status == "skipped"


def test_control_trials_are_idempotent(store, db_engine):
    clip_row(db_engine)
    store.start(run_id="r1", session_id="s1", plan=plan(), now=NOW)
    pairs = [("sound.sub.v.w", Detector.AZURE_PA)]
    store.add_control_trials("r1", "abc", pairs)
    store.add_control_trials("r1", "abc", pairs)
    controls = [t for t in store.trials("r1") if t.trial.tts_hash == "abc"]
    assert len(controls) == 1


def test_control_analyses_are_stored_once_per_run(store, db_engine):
    clip_row(db_engine)
    store.start(run_id="r1", session_id="s1", plan=plan(), now=NOW)
    raw = RawResult("azure", "v", "azure_pa", 1, {"x": 1})
    assert store.control_analysis("abc", "r1", AnalysisKind.PRONUNCIATION) is None
    store.add_control_analysis("abc", "r1", AnalysisKind.PRONUNCIATION, raw)
    store.add_control_analysis("abc", "r1", AnalysisKind.PRONUNCIATION, raw)
    found = store.control_analysis("abc", "r1", AnalysisKind.PRONUNCIATION)
    assert found is not None and dict(found.payload) == {"x": 1}


def test_complete_writes_the_config_and_marks_the_run_done(store, db_engine):
    store.start(run_id="r1", session_id="s1", plan=plan(), now=NOW)
    config = build_calibrated_config(config_id="cfg", run_id="r1", results=[])
    store.complete(run_id="r1", config=config, capabilities={"azure_pa": {}}, now=NOW)
    run = store.latest()
    assert run is not None and run.status == "done" and run.scoring_config_id == "cfg"
    assert ScoringConfigRepository(db_engine, TAX).get("cfg").kind is ConfigKind.CALIBRATED


def test_open_calibrate_job_finds_a_queued_job(store, db_engine):
    assert store.open_calibrate_job() is None
    job = SqliteJobQueue(db_engine, clock=FixedClock(T0)).enqueue(JobKind.CALIBRATE, None)
    assert store.open_calibrate_job() == job.id
