"""Properties of the calibration rule over generated trial counts."""

import random
from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from nosolear.domain.calibration import Trial, TrialKind, build_calibrated_config, evaluate, passes
from nosolear.domain.scoring import V0_CONFIG, TrialCounts
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as TAX
from nosolear.domain.taxonomy import Detector


@st.composite
def counts(draw: st.DrawFn, max_errors: int = 20, max_controls: int = 20) -> TrialCounts:
    errors = draw(st.integers(0, max_errors))
    controls = draw(st.integers(0, max_controls))
    return TrialCounts(
        errors=errors,
        hits=draw(st.integers(0, errors)),
        controls=controls,
        false_alarms=draw(st.integers(0, controls)),
        correct_takes=draw(st.integers(0, 20)),
        correct_flags=draw(st.integers(0, 20)),
    )


def _with_correct_takes(c: TrialCounts, takes: int, flags: int) -> TrialCounts:
    return replace(c, correct_takes=takes, correct_flags=min(flags, takes))


@given(c=counts())
def test_enabled_iff_rule(c: TrialCounts):
    expected = (
        c.errors >= 5
        and c.controls >= 5
        and 5 * c.hits >= 4 * c.errors
        and 5 * c.false_alarms <= c.controls
    )
    assert passes(c) == expected


@given(c=counts())
def test_adding_a_hit_never_disables(c: TrialCounts):
    assert not passes(c) or passes(replace(c, errors=c.errors + 1, hits=c.hits + 1))


@given(c=counts())
def test_adding_a_miss_or_a_false_alarm_never_enables(c: TrialCounts):
    if not passes(c):
        assert not passes(replace(c, errors=c.errors + 1))
        assert not passes(replace(c, controls=c.controls + 1, false_alarms=c.false_alarms + 1))


@given(c=counts())
def test_adding_a_clean_control_never_disables(c: TrialCounts):
    assert not passes(c) or passes(replace(c, controls=c.controls + 1))


@given(c=counts(), takes=st.integers(0, 20), flags=st.integers(0, 20))
def test_correct_takes_never_change_enablement(c: TrialCounts, takes: int, flags: int):
    assert passes(c) == passes(_with_correct_takes(c, takes, flags))


@given(c=counts(max_errors=4))
def test_too_few_error_trials_never_enable(c: TrialCounts):
    assert not passes(c)


@given(c=counts(max_controls=4))
def test_too_few_controls_never_enable(c: TrialCounts):
    assert not passes(c)


TRIAL_KEYS = ["sound.sub.v.w", "sound.sub.f.p"]


@st.composite
def trial_lists(draw: st.DrawFn) -> list[Trial]:
    out: list[Trial] = []
    for n in range(draw(st.integers(0, 30))):
        key = draw(st.sampled_from(TRIAL_KEYS))
        flag = draw(st.one_of(st.none(), st.booleans()))
        if draw(st.booleans()):
            out.append(Trial(key, Detector.AZURE_PA, TrialKind.ERROR, f"a{n}", None, flag))
        elif draw(st.booleans()):
            out.append(Trial(key, Detector.AZURE_PA, TrialKind.CONTROL, None, f"t{n % 7}", flag))
        else:
            out.append(Trial(key, Detector.AZURE_PA, TrialKind.CONTROL, f"c{n}", None, flag))
    return out


@given(ts=trial_lists(), seed=st.randoms())
def test_evaluate_is_order_independent(ts: list[Trial], seed: random.Random):
    shuffled = list(ts)
    seed.shuffle(shuffled)
    assert evaluate(ts) == evaluate(shuffled)


@given(ts=trial_lists())
def test_calibrated_config_enables_exactly_passing_covered_pairs(ts: list[Trial]):
    results = evaluate(ts)
    cfg = build_calibrated_config(config_id="c", run_id="r", results=results)
    for result in results:
        definition = TAX.get(result.error_key)
        rule = cfg.rule_for(result.detector, definition)
        if result.covered:
            assert (rule is not None) == passes(result.counts)
        else:
            assert rule == V0_CONFIG.rule_for(result.detector, definition)
