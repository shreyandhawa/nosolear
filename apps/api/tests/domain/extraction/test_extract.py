"""The `extract` entry point: every detector combined into observations under one config."""

from dataclasses import replace

from factories import (
    PACK,
    T0,
    TAX,
    coach_analysis,
    finding,
    pa_phone,
    pa_result,
    pa_word,
    probe_result,
    transcript_from,
)

from nosolear.domain.extraction.extract import ExtractionItem, ProviderResults, extract
from nosolear.domain.observations import Context, Outcome
from nosolear.domain.scoring import (
    CALIBRATED_THRESHOLDS,
    V0_CONFIG,
    ConfigKind,
    KeyRule,
    ScoringConfig,
    TrialCounts,
)
from nosolear.domain.taxonomy import Detector

VEST_AS_WEST = pa_result(
    [
        pa_word(
            "vest",
            [
                pa_phone("v", 30, [("w", 80), ("v", 40)]),
                pa_phone("ɛ", 95),
                pa_phone("s", 95),
                pa_phone("t", 95),
            ],
        )
    ]
)
TEXT = transcript_from("I go to the market yesterday.")
FULL = ProviderResults(
    pronunciation=VEST_AS_WEST,
    transcript=TEXT,
    phone_probe=probe_result("vest", [["v", "ɛ", "s", "t"]], ["w", "ɛ", "s", "t"]),
    coach=coach_analysis([finding("grammar.verb_tense", "I go to")]),
)
COUNTS = TrialCounts(errors=5, hits=5, controls=5, false_alarms=0, correct_takes=0, correct_flags=0)
CAL_CONFIG = ScoringConfig(
    id="c1",
    kind=ConfigKind.CALIBRATED,
    calibration_run_id="r1",
    thresholds=CALIBRATED_THRESHOLDS,
    family_rules=(),
    key_rules=(KeyRule(Detector.AZURE_PA, "sound.sub.v.w", True, CALIBRATED_THRESHOLDS, COUNTS),),
)


def item(step: str = "read_aloud", scripted: bool = True) -> ExtractionItem:
    return ExtractionItem("a", step, scripted, "The vest.", T0)


def run(it: ExtractionItem, results: ProviderResults, config: ScoringConfig = V0_CONFIG):
    return extract(it, results, config=config, pack=PACK, taxonomy=TAX)


def test_calibration_attempts_yield_nothing() -> None:
    assert run(ExtractionItem("a", "calibration", True, "vest", T0), FULL) == {}


def test_observations_carry_config_and_provisional() -> None:
    out = run(item("read_aloud"), ProviderResults(pronunciation=VEST_AS_WEST))
    assert set(out) == {Detector.AZURE_PA}
    vw = [o for o in out[Detector.AZURE_PA] if o.error_key == "sound.sub.v.w"]
    assert vw and all(
        o.scoring_config_id == "v0" and o.provisional and o.attempt_id == "a" for o in vw
    )
    assert all(o.outcome is Outcome.MISS for o in vw)


def test_phone_probe_is_drill_only_under_v0() -> None:
    out = run(item("drill"), ProviderResults(phone_probe=FULL.phone_probe))
    assert out[Detector.PHONE_PROBE] == ()


def test_calibrated_key_is_firm() -> None:
    out = run(item("read_aloud"), ProviderResults(pronunciation=VEST_AS_WEST), CAL_CONFIG)
    vw = [o for o in out[Detector.AZURE_PA] if o.error_key == "sound.sub.v.w"]
    assert vw and all(not o.provisional and o.scoring_config_id == "c1" for o in vw)


def test_disabled_key_writes_nothing() -> None:
    off = replace(CAL_CONFIG, key_rules=(replace(CAL_CONFIG.key_rules[0], enabled=False),))
    out = run(item("read_aloud"), ProviderResults(pronunciation=VEST_AS_WEST), off)
    assert not [o for o in out[Detector.AZURE_PA] if o.error_key == "sound.sub.v.w"]


def test_unscripted_sound_evidence_weighs_half() -> None:
    out = run(item("speak", scripted=False), ProviderResults(pronunciation=VEST_AS_WEST))
    assert out[Detector.AZURE_PA] and all(
        o.context is Context.UNSCRIPTED for o in out[Detector.AZURE_PA]
    )
    assert all(o.weight == 0.5 for o in out[Detector.AZURE_PA])


def test_coach_without_transcript_is_empty() -> None:
    out = run(item("speak", scripted=False), ProviderResults(coach=FULL.coach))
    assert out[Detector.COACH] == ()


def test_each_present_detector_has_an_entry_even_when_empty() -> None:
    out = run(item("quick_answer", scripted=False), FULL)
    assert set(out) == {
        Detector.AZURE_PA,
        Detector.PHONE_PROBE,
        Detector.ASR_METRICS,
        Detector.COACH,
    }
    assert out[Detector.ASR_METRICS]
