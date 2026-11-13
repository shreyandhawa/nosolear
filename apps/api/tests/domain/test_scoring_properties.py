import json

from factories import TAX
from hypothesis import given
from strategies import (
    CONFIG_ORDER,
    all_keys,
    attempt_observations,
    detectors,
    scored_pairs,
    scoring_configs,
)

from nosolear.domain.scoring import (
    SOUND_FAMILIES,
    V0_CONFIG,
    ConfigKind,
    ScoringConfig,
    ScoringRule,
    canonical_json,
    current_observations,
    rules_from_json,
    rules_to_json,
)
from nosolear.domain.taxonomy import Detector


@given(config=scoring_configs(), key=all_keys(), detector=detectors())
def test_rule_for_follows_key_rules_then_family_rules(config: ScoringConfig, key, detector):
    definition = TAX.get(key)
    rule = config.rule_for(detector, definition)
    if detector not in definition.detectors:
        assert rule is None
        return
    key_rule = next(
        (r for r in config.key_rules if r.error_key == key and r.detector == detector), None
    )
    if key_rule is not None:
        expected = ScoringRule(False, key_rule.thresholds) if key_rule.enabled else None
        assert rule == expected
        return
    family_rule = next(
        (
            r
            for r in config.family_rules
            if r.detector == detector and r.family == definition.family
        ),
        None,
    )
    if family_rule is not None and family_rule.enabled:
        assert rule == ScoringRule(family_rule.provisional, config.thresholds)
    else:
        assert rule is None


@given(key=all_keys(), detector=detectors())
def test_v0_provisional_exactly_for_sound_and_prosody(key, detector):
    definition = TAX.get(key)
    rule = V0_CONFIG.rule_for(detector, definition)
    if detector is Detector.PHONE_PROBE:
        assert rule is None
    if rule is not None:
        assert rule.provisional == (definition.family in SOUND_FAMILIES)


@given(config=scoring_configs())
def test_rules_json_round_trip(config: ScoringConfig):
    rules = rules_to_json(config)
    text = canonical_json(rules)
    assert text == canonical_json(rules_to_json(config))
    back = rules_from_json(
        config_id=config.id,
        kind=config.kind,
        calibration_run_id=config.calibration_run_id,
        rules=json.loads(text),
        taxonomy=TAX,
    )
    assert back == config
    if config.kind is ConfigKind.V0:
        assert back.calibration_run_id is None


@given(obs=attempt_observations(), scored=scored_pairs())
def test_current_observations_keeps_one_config_per_attempt(obs, scored):
    kept = current_observations(obs, scored=scored, config_order=CONFIG_ORDER)

    rank = {config: i for i, config in enumerate(CONFIG_ORDER)}
    newest: dict[str, str] = {}
    for attempt_id, config_id in scored:
        if attempt_id not in newest or rank[config_id] > rank[newest[attempt_id]]:
            newest[attempt_id] = config_id

    # Result is a subsequence of the input (order preserved, nothing invented).
    position = 0
    for item in kept:
        while position < len(obs) and obs[position] is not item:
            position += 1
        assert position < len(obs)
        position += 1

    expected = [
        o
        for o in obs
        if o.attempt_id is None
        or o.attempt_id not in newest
        or o.scoring_config_id == newest[o.attempt_id]
    ]
    assert kept == expected
    for item in kept:
        if item.attempt_id in newest:
            assert item.scoring_config_id == newest[item.attempt_id]
