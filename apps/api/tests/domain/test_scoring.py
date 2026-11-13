from dataclasses import replace
from typing import Any

import pytest
from factories import T0, TAX, mk

from nosolear.domain.observations import Outcome
from nosolear.domain.scoring import (
    CALIBRATED_THRESHOLDS,
    V0_CONFIG,
    V0_THRESHOLDS,
    ConfigKind,
    FamilyRule,
    KeyRule,
    ScoringConfig,
    ScoringConfigInvalid,
    ScoringRule,
    Thresholds,
    TrialCounts,
    current_observations,
    rules_from_json,
    rules_to_json,
)
from nosolear.domain.taxonomy import Detector

MISS, OK = Outcome.MISS, Outcome.OK
K = "sound.sub.v.w"

V0_RULES_JSON = {
    "schema": 1,
    "thresholds": {
        "nbest_margin": 30.0,
        "low_accuracy": 40.0,
        "slow_start_ms": 3000,
        "long_pause_ms": 2000,
    },
    "family_rules": [
        {"detector": "asr_metrics", "family": "fluency", "enabled": True, "provisional": False},
        {"detector": "azure_pa", "family": "prosody", "enabled": True, "provisional": True},
        {"detector": "azure_pa", "family": "sound.low", "enabled": True, "provisional": True},
        {"detector": "azure_pa", "family": "sound.sub", "enabled": True, "provisional": True},
        {"detector": "coach", "family": "clarity", "enabled": True, "provisional": False},
        {"detector": "coach", "family": "grammar", "enabled": True, "provisional": False},
        {"detector": "coach", "family": "structure", "enabled": True, "provisional": False},
        {"detector": "phone_probe", "family": "sound.del", "enabled": False, "provisional": True},
        {"detector": "phone_probe", "family": "sound.ins", "enabled": False, "provisional": True},
        {"detector": "phone_probe", "family": "sound.sub", "enabled": False, "provisional": True},
    ],
    "key_rules": [],
}

COUNTS = TrialCounts(
    errors=10, hits=8, controls=10, false_alarms=1, correct_takes=4, correct_flags=0
)


def key_rule_json(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "error_key": "sound.sub.v.w",
        "detector": "azure_pa",
        "enabled": True,
        "thresholds": {
            "nbest_margin": 15.0,
            "low_accuracy": 60.0,
            "slow_start_ms": 3000,
            "long_pause_ms": 2000,
        },
        "counts": {
            "errors": 10,
            "hits": 8,
            "controls": 10,
            "false_alarms": 1,
            "correct_takes": 4,
            "correct_flags": 0,
        },
    }
    if "nbest_margin" in overrides:
        base["thresholds"]["nbest_margin"] = overrides.pop("nbest_margin")
    if "hits" in overrides:
        base["counts"]["hits"] = overrides.pop("hits")
    if "errors" in overrides:
        base["counts"]["errors"] = overrides.pop("errors")
    base.update(overrides)
    return base


def calibrated(key_rules: tuple[KeyRule, ...] = ()) -> ScoringConfig:
    return ScoringConfig(
        id="c1",
        kind=ConfigKind.CALIBRATED,
        calibration_run_id="r1",
        thresholds=CALIBRATED_THRESHOLDS,
        family_rules=V0_CONFIG.family_rules,
        key_rules=key_rules,
    )


def test_v0_rules_json_is_pinned():
    assert rules_to_json(V0_CONFIG) == V0_RULES_JSON


V0 = ScoringRule(provisional=True, thresholds=V0_THRESHOLDS)
FIRM = ScoringRule(provisional=False, thresholds=V0_THRESHOLDS)


@pytest.mark.parametrize(
    "key, detector, expected",
    [
        ("sound.sub.v.w", Detector.AZURE_PA, V0),
        ("sound.sub.p.b", Detector.AZURE_PA, V0),
        ("sound.low.θ", Detector.AZURE_PA, V0),
        ("prosody.monotone", Detector.AZURE_PA, V0),
        ("sound.sub.v.w", Detector.PHONE_PROBE, None),
        ("sound.ins.epenthesis_sC", Detector.PHONE_PROBE, None),
        ("sound.del.final_cluster", Detector.AZURE_PA, None),
        ("prosody.word_stress", Detector.AZURE_PA, None),
        ("fluency.filler", Detector.ASR_METRICS, FIRM),
        ("grammar.article", Detector.COACH, FIRM),
    ],
)
def test_v0_rule_table(key, detector, expected):
    assert V0_CONFIG.rule_for(detector, TAX.get(key)) == expected


def test_v0_is_stricter_than_calibrated():
    assert V0_THRESHOLDS.nbest_margin > CALIBRATED_THRESHOLDS.nbest_margin
    assert V0_THRESHOLDS.low_accuracy < CALIBRATED_THRESHOLDS.low_accuracy


def test_key_rule_overrides_family_rule_and_is_never_provisional():
    c = calibrated(
        key_rules=(
            KeyRule(Detector.AZURE_PA, "sound.sub.v.w", True, CALIBRATED_THRESHOLDS, COUNTS),
            KeyRule(Detector.AZURE_PA, "sound.sub.f.p", False, CALIBRATED_THRESHOLDS, COUNTS),
        )
    )
    assert c.rule_for(Detector.AZURE_PA, TAX.get("sound.sub.v.w")) == ScoringRule(
        False, CALIBRATED_THRESHOLDS
    )
    assert c.rule_for(Detector.AZURE_PA, TAX.get("sound.sub.f.p")) is None
    # uncovered key: falls back to the family rule, which is provisional
    assert c.rule_for(Detector.AZURE_PA, TAX.get("sound.sub.θ.t")) == ScoringRule(
        True, CALIBRATED_THRESHOLDS
    )


@pytest.mark.parametrize(
    "bad",
    [
        {**key_rule_json(), "error_key": "grammar.artcle"},
        {**key_rule_json(), "detector": "coach"},
        key_rule_json(hits=11, errors=10),
        key_rule_json(nbest_margin=float("nan")),
    ],
)
def test_rules_from_json_rejects_bad_key_rules(bad):
    rules = {**V0_RULES_JSON, "key_rules": [bad]}
    with pytest.raises(ScoringConfigInvalid):
        rules_from_json(
            config_id="c",
            kind=ConfigKind.CALIBRATED,
            calibration_run_id="r",
            rules=rules,
            taxonomy=TAX,
        )


def test_rules_from_json_rejects_unknown_schema():
    with pytest.raises(ScoringConfigInvalid):
        rules_from_json(
            config_id="v0",
            kind=ConfigKind.V0,
            calibration_run_id=None,
            rules={**V0_RULES_JSON, "schema": 2},
            taxonomy=TAX,
        )


def test_kind_and_run_id_must_agree():
    with pytest.raises(ScoringConfigInvalid):
        replace(V0_CONFIG, calibration_run_id="r")


def test_duplicate_family_rule_is_rejected():
    first = V0_CONFIG.family_rules[0]
    dup = FamilyRule(first.detector, first.family, not first.enabled, first.provisional)
    with pytest.raises(ScoringConfigInvalid):
        replace(V0_CONFIG, family_rules=(*V0_CONFIG.family_rules, dup))


def test_keeps_only_the_newest_config_that_scored_each_attempt():
    a1_v0 = mk(K, MISS, T0, attempt_id="a1")
    a1_c1 = mk(K, OK, T0, attempt_id="a1", scoring_config_id="c1")
    a2_v0 = mk(K, MISS, T0, attempt_id="a2")
    free = mk(K, MISS, T0)
    kept = current_observations(
        [a1_v0, a1_c1, a2_v0, free],
        scored=[("a1", "v0"), ("a1", "c1"), ("a2", "v0")],
        config_order=["v0", "c1"],
    )
    assert kept == [a1_c1, a2_v0, free]


def test_newer_config_with_no_observations_still_wins():
    kept = current_observations(
        [mk(K, MISS, T0, attempt_id="a1")],
        scored=[("a1", "v0"), ("a1", "c1")],
        config_order=["v0", "c1"],
    )
    assert kept == []


def test_thresholds_are_a_value_type():
    assert Thresholds(30.0, 40.0, 3000, 2000) == V0_THRESHOLDS
