"""The calibration rule, its planning and the calibrated config (ARCHITECTURE.md section 9.2)."""

from fractions import Fraction

import pytest
from factories import pa_phone, pa_result, pa_word, probe_result

from nosolear.domain.calibration import (
    DEFAULT_RULE,
    CalibrationRule,
    PairResult,
    Trial,
    TrialKind,
    build_calibrated_config,
    calibratable_detectors,
    covers,
    evaluate,
    flagged,
    passes,
    plan_calibration,
    tally,
)
from nosolear.domain.calibration_items import CalibrationSpec
from nosolear.domain.content import CalibrationSet, calibration_set
from nosolear.domain.scoring import (
    CALIBRATED_THRESHOLDS,
    V0_CONFIG,
    ConfigKind,
    TrialCounts,
)
from nosolear.domain.speech import PronunciationAssessment
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as TAX
from nosolear.domain.taxonomy import Detector


def counts(**overrides: int) -> TrialCounts:
    base = {"errors": 0, "hits": 0, "controls": 0, "false_alarms": 0, "correct_takes": 0,
            "correct_flags": 0}  # fmt: skip
    base.update(overrides)
    return TrialCounts(**base)


def vest_said_as_west() -> PronunciationAssessment:
    return pa_result(
        [
            pa_word(
                "vest",
                [
                    pa_phone("v", 30, [("w", 80), ("v", 40)]),
                    pa_phone("ɛ", 95, [("ɛ", 95)]),
                ],
            )
        ]
    )


def vest_said_correctly() -> PronunciationAssessment:
    return pa_result([pa_word("vest", [pa_phone("v", 95, [("v", 95)])])])


def trial(error_key: str, *, attempt: str | None = None, tts: str | None = None,
          kind: TrialKind = TrialKind.CONTROL, flag: bool | None = None,
          detector: Detector = Detector.AZURE_PA) -> Trial:  # fmt: skip
    return Trial(error_key, detector, kind, attempt, tts, flag)


def test_rule_boundaries():
    assert passes(counts(errors=10, hits=8, controls=5, false_alarms=1))
    assert not passes(counts(errors=10, hits=7, controls=5, false_alarms=1))
    assert not passes(counts(errors=10, hits=8, controls=5, false_alarms=2))
    assert not passes(counts(errors=4, hits=4, controls=5))
    assert not passes(counts(errors=10, hits=10, controls=4))


def test_default_rule_values():
    assert CalibrationRule(5, 5, Fraction(4, 5), Fraction(1, 5)) == DEFAULT_RULE
    assert covers(counts(errors=5, controls=5))


def test_flagged_azure_substitution():
    assert (
        flagged(Detector.AZURE_PA, "sound.sub.v.w", vest_said_as_west(), reference_text="vest")
        is True
    )
    assert (
        flagged(Detector.AZURE_PA, "sound.sub.v.w", vest_said_correctly(), reference_text="vest")
        is False
    )


def test_flagged_is_none_without_an_opportunity():
    fan = pa_result([pa_word("fan", [pa_phone("f", 95, [("f", 95)])])])
    assert flagged(Detector.AZURE_PA, "sound.sub.v.w", fan, reference_text="fan") is None


def test_no_nbest_means_no_trial_counted():
    no_nbest = pa_result([pa_word("vest", [pa_phone("v", 30, [])])], has_nbest=False)
    assert flagged(Detector.AZURE_PA, "sound.sub.v.w", no_nbest, reference_text="vest") is None


def test_flagged_probe_substitution():
    result = probe_result("vest", [["v", "ɛ", "s", "t"]], ["w", "ɛ", "s", "t"])
    assert flagged(Detector.PHONE_PROBE, "sound.sub.v.w", result, reference_text="vest") is True


def test_flagged_probe_epenthesis():
    result = probe_result("school", [["s", "k", "u", "l"]], ["ɪ", "s", "k", "u", "l"])
    assert (
        flagged(Detector.PHONE_PROBE, "sound.ins.epenthesis_sC", result, reference_text="school")
        is True
    )


def test_tally_follows_the_trial_rules():
    trials = [
        trial("sound.sub.v.w", attempt="a1", kind=TrialKind.ERROR, flag=True),
        trial("sound.sub.v.w", attempt="a2", kind=TrialKind.ERROR, flag=False),
        trial("sound.sub.v.w", tts="h1", flag=True),
        trial("sound.sub.v.w", attempt="c1", flag=True),
        trial("sound.sub.v.w", attempt="c2", flag=None),
    ]
    (count,) = tally(trials).values()
    assert count == counts(
        errors=2, hits=1, controls=1, false_alarms=1, correct_takes=1, correct_flags=1
    )


def test_trial_needs_exactly_one_subject():
    with pytest.raises(ValueError):
        Trial("sound.sub.v.w", Detector.AZURE_PA, TrialKind.CONTROL, "a", "h", True)
    with pytest.raises(ValueError):
        Trial("sound.sub.v.w", Detector.AZURE_PA, TrialKind.ERROR, None, "h", True)


def test_correct_take_flags_warn_but_do_not_disable():
    trials = [
        trial("sound.sub.v.w", attempt=f"e{i}", kind=TrialKind.ERROR, flag=True) for i in range(10)
    ]
    trials += [trial("sound.sub.v.w", tts=f"t{i}", flag=False) for i in range(5)]
    trials += [trial("sound.sub.v.w", attempt=f"c{i}", flag=i < 3) for i in range(5)]
    (result,) = evaluate(trials)
    assert result.enabled
    assert result.warning == (
        "Your own correct takes were flagged 60% of the time (TTS controls: 0%). "
        "This detector may count errors you didn't make on this key."
    )


def test_evaluate_reports_uncovered_pairs_without_enabling_them():
    trials = [trial("sound.sub.f.p", attempt="e1", kind=TrialKind.ERROR, flag=True)]
    (result,) = evaluate(trials)
    assert isinstance(result, PairResult)
    assert result.covered is False and result.enabled is False and result.warning is None
    assert result.hit_rate == 1.0 and result.false_alarm_rate is None


def test_calibrated_config_covers_only_covered_pairs():
    enabled = PairResult(
        Detector.AZURE_PA, "sound.sub.v.w", counts(errors=5, hits=5, controls=5), True, True, None
    )
    failed = PairResult(
        Detector.AZURE_PA, "sound.sub.f.p", counts(errors=5, hits=0, controls=5), True, False, None
    )
    uncovered = PairResult(Detector.AZURE_PA, "sound.sub.θ.t", counts(errors=2), False, False, None)
    cfg = build_calibrated_config(config_id="c1", run_id="r1", results=[enabled, failed, uncovered])
    assert cfg.kind is ConfigKind.CALIBRATED
    assert {(k.error_key, k.enabled) for k in cfg.key_rules} == {
        ("sound.sub.v.w", True),
        ("sound.sub.f.p", False),
    }
    for key_rule in cfg.key_rules:
        assert key_rule.thresholds == CALIBRATED_THRESHOLDS
    theta = TAX.get("sound.sub.θ.t")
    assert cfg.rule_for(Detector.AZURE_PA, theta) == V0_CONFIG.rule_for(Detector.AZURE_PA, theta)


def test_plan_orders_by_pack_emphasis_and_drops_keys_without_detectors():
    cs = calibration_set(
        [
            CalibrationSpec("sound.sub.v.w", "W instead of V", (("vest", "west"),)),
            CalibrationSpec("sound.sub.f.p", "P instead of F", (("fan", "pan"),)),
            CalibrationSpec(
                "sound.ins.epenthesis_sC", "a vowel before it", (("school", "ischool"),)
            ),
        ]
    )
    plan = plan_calibration(
        cs,
        emphasis=["sound.sub.f.p"],
        available=frozenset({Detector.AZURE_PA}),
        taxonomy=TAX,
    )
    assert list(plan.detectors) == ["sound.sub.f.p", "sound.sub.v.w"]
    assert [(t.word, t.deliberate, t.take) for t in plan.tokens[:3]] == [
        ("fan", False, 1),
        ("fan", True, 1),
        ("fan", True, 2),
    ]
    assert [t.order for t in plan.tokens] == list(range(1, len(plan.tokens) + 1))


def test_plan_is_empty_with_no_detectors():
    cs: CalibrationSet = calibration_set(
        [CalibrationSpec("sound.sub.v.w", "d", (("vest", "west"),))]
    )
    plan = plan_calibration(cs, emphasis=[], available=frozenset(), taxonomy=TAX)
    assert plan.tokens == () and plan.detectors == {}


def test_calibratable_detectors():
    assert calibratable_detectors(azure_nbest=False, phone_probe_ready=False) == frozenset()
    assert calibratable_detectors(azure_nbest=True, phone_probe_ready=False) == frozenset(
        {Detector.AZURE_PA}
    )
    assert calibratable_detectors(azure_nbest=False, phone_probe_ready=True) == frozenset(
        {Detector.PHONE_PROBE}
    )
