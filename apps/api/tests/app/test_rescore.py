"""Re-scoring stored history: no provider call, no quota, newest config per attempt."""

import inspect
from typing import Any

from factories import PACK, T0, TAX
from harness import Harness
from sqlalchemy import insert

from nosolear.app.rescore import rescore
from nosolear.domain.profile import Profile
from nosolear.domain.scoring import (
    CALIBRATED_THRESHOLDS,
    V0_FAMILY_RULES,
    ConfigKind,
    KeyRule,
    ScoringConfig,
    TrialCounts,
)
from nosolear.domain.taxonomy import Detector
from nosolear.persistence.models import calibration_runs
from nosolear.persistence.repositories import ObservationRepository, ProfileRepository
from nosolear.persistence.scoring_repository import (
    ExtractionInputsRepository,
    ExtractionRepository,
    ScoringConfigRepository,
)

CAL_CONFIG = ScoringConfig(
    id="c1",
    kind=ConfigKind.CALIBRATED,
    calibration_run_id="r1",
    thresholds=CALIBRATED_THRESHOLDS,
    family_rules=V0_FAMILY_RULES,
    key_rules=(
        KeyRule(
            Detector.AZURE_PA,
            "sound.sub.v.w",
            True,
            CALIBRATED_THRESHOLDS,
            TrialCounts(
                errors=5, hits=5, controls=5, false_alarms=0, correct_takes=0, correct_flags=0
            ),
        ),
    ),
)


def add_config(h: Harness, config: ScoringConfig) -> None:
    assert config.calibration_run_id is not None
    with h.engine.begin() as conn:
        conn.execute(
            insert(calibration_runs).values(
                id=config.calibration_run_id,
                session_id=None,
                status="done",
                scoring_config_id=None,
                started_at=T0,
                completed_at=T0,
            )
        )
    ScoringConfigRepository(h.engine, TAX).add(config, capabilities={}, created_at=T0)


def scored_baseline_attempt(h: Harness) -> str:
    a = h.attempt(step="read_aloud", scripted=True, reference_text="Seven vans.")
    h.voice.user_errors["v"] = "w"
    h.upload(a, "Seven vans.")
    h.drain()
    return a


def rescore_deps(h: Harness) -> dict[str, Any]:
    return {
        "inputs": ExtractionInputsRepository(h.engine),
        "configs": ScoringConfigRepository(h.engine, TAX),
        "extractions": ExtractionRepository(h.engine),
        "observations": ObservationRepository(h.engine),
        "profiles": ProfileRepository(h.engine, TAX),
        "pack": PACK,
        "taxonomy": TAX,
        "clock": h.clock,
    }


def _entry(profile: Profile | None, key: str) -> Any:
    assert profile is not None
    return next(e for e in profile.entries if e.definition.key == key)


def test_rescore_makes_no_provider_calls_and_spends_no_quota(harness: Harness) -> None:
    a = scored_baseline_attempt(harness)
    calls = sum(harness.voice.calls.values())
    ledger = harness.ledger_rows()
    harness.voice.fail_all(AssertionError("provider called during re-score"))
    add_config(harness, CAL_CONFIG)
    summary = rescore(**rescore_deps(harness))
    assert summary.attempts == 1 and summary.scoring_config_id == CAL_CONFIG.id
    assert sum(harness.voice.calls.values()) == calls
    assert harness.ledger_rows() == ledger
    current = ObservationRepository(harness.engine).current()
    assert {o.scoring_config_id for o in current if o.attempt_id == a} == {CAL_CONFIG.id}
    assert any(o.scoring_config_id == "v0" for o in ObservationRepository(harness.engine).all())


def test_rescore_is_idempotent(harness: Harness) -> None:
    scored_baseline_attempt(harness)
    add_config(harness, CAL_CONFIG)
    first = rescore(**rescore_deps(harness))
    second = rescore(**rescore_deps(harness))
    assert first.observations > 0
    assert second.observations == 0


def test_rescore_skips_calibration_attempts(harness: Harness) -> None:
    cal = harness.attempt(step="calibration", scripted=True, reference_text="Seven vans.")
    harness.upload(cal, "Seven vans.")
    harness.drain()
    add_config(harness, CAL_CONFIG)
    summary = rescore(**rescore_deps(harness))
    assert summary.attempts == 0
    assert summary.observations == 0


def test_profile_uses_newest_config_per_attempt(harness: Harness) -> None:
    scored_baseline_attempt(harness)
    profiles = ProfileRepository(harness.engine, TAX)
    before = _entry(profiles.latest(), "sound.sub.v.w")
    add_config(harness, CAL_CONFIG)
    rescore(**rescore_deps(harness))
    after = _entry(profiles.latest(), "sound.sub.v.w")
    assert before.provisional is True
    assert after.provisional is False


def test_rescore_signature_has_no_provider_port() -> None:
    parameters = set(inspect.signature(rescore).parameters)
    assert not {"scorer", "transcriber", "probe", "synthesizer", "coach"} & parameters
