"""Hypothesis strategies for scoring configs and observations. Import from `strategies`."""

from factories import T0, TAX, mk
from hypothesis import strategies as st

from nosolear.domain.observations import Observation, Outcome
from nosolear.domain.scoring import (
    ConfigKind,
    FamilyRule,
    KeyRule,
    ScoringConfig,
    Thresholds,
    TrialCounts,
)
from nosolear.domain.taxonomy import Detector, Family

ATTEMPTS = ("a0", "a1", "a2", "a3", "a4")
CONFIG_ORDER = ("v0", "c1", "c2")
_FAMILY_PAIRS = [(d, f) for d in Detector for f in Family]
_KEYS = sorted(d.key for d in TAX.defined())


def detectors() -> st.SearchStrategy[Detector]:
    return st.sampled_from(list(Detector))


def all_keys() -> st.SearchStrategy[str]:
    return st.sampled_from([*_KEYS, "sound.sub.θ.ɹ", "sound.low.ʃ", "sound.sub.ɪ.æ"])


def scorable_keys() -> st.SearchStrategy[str]:
    """Keys with at least one detector; a key with none (prosody.word_stress) cannot be observed."""
    return all_keys().filter(lambda k: bool(TAX.get(k).detectors))


def sound_keys() -> st.SearchStrategy[str]:
    return all_keys().filter(lambda k: TAX.get(k).family.value.startswith("sound."))


def thresholds() -> st.SearchStrategy[Thresholds]:
    finite = st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
    return st.builds(
        Thresholds,
        nbest_margin=finite,
        low_accuracy=finite,
        slow_start_ms=st.integers(min_value=0, max_value=60_000),
        long_pause_ms=st.integers(min_value=0, max_value=60_000),
    )


@st.composite
def trial_counts(draw: st.DrawFn) -> TrialCounts:
    errors = draw(st.integers(min_value=0, max_value=50))
    controls = draw(st.integers(min_value=0, max_value=50))
    takes = draw(st.integers(min_value=0, max_value=20))
    return TrialCounts(
        errors=errors,
        hits=draw(st.integers(min_value=0, max_value=errors)),
        controls=controls,
        false_alarms=draw(st.integers(min_value=0, max_value=controls)),
        correct_takes=takes,
        correct_flags=draw(st.integers(min_value=0, max_value=takes)),
    )


def _family_rules() -> st.SearchStrategy[tuple[FamilyRule, ...]]:
    rule = st.tuples(st.sampled_from(_FAMILY_PAIRS), st.booleans(), st.booleans())
    return st.lists(rule, max_size=12, unique_by=lambda t: t[0]).map(
        lambda picked: tuple(
            sorted(
                (FamilyRule(pair[0], pair[1], enabled, prov) for pair, enabled, prov in picked),
                key=lambda r: (r.detector, r.family),
            )
        )
    )


def _key_and_detector() -> st.SearchStrategy[tuple[str, Detector]]:
    return scorable_keys().flatmap(
        lambda key: st.sampled_from(sorted(TAX.get(key).detectors, key=lambda d: d.value)).map(
            lambda detector: (key, detector)
        )
    )


def _key_rules() -> st.SearchStrategy[tuple[KeyRule, ...]]:
    item = st.tuples(_key_and_detector(), st.booleans(), thresholds(), trial_counts())
    return st.lists(item, max_size=5, unique_by=lambda t: t[0]).map(
        lambda picked: tuple(
            sorted(
                (
                    KeyRule(detector, key, enabled, limits, counts)
                    for (key, detector), enabled, limits, counts in picked
                ),
                key=lambda r: (r.error_key, r.detector),
            )
        )
    )


@st.composite
def scoring_configs(draw: st.DrawFn) -> ScoringConfig:
    if draw(st.booleans()):
        return ScoringConfig(
            id="v0",
            kind=ConfigKind.V0,
            calibration_run_id=None,
            thresholds=draw(thresholds()),
            family_rules=draw(_family_rules()),
            key_rules=draw(_key_rules()),
        )
    return ScoringConfig(
        id="c1",
        kind=ConfigKind.CALIBRATED,
        calibration_run_id="r1",
        thresholds=draw(thresholds()),
        family_rules=draw(_family_rules()),
        key_rules=draw(_key_rules()),
    )


@st.composite
def observations(draw: st.DrawFn) -> Observation:
    key = draw(scorable_keys())
    detector = draw(st.sampled_from(sorted(TAX.get(key).detectors, key=lambda d: d.value)))
    return mk(
        key,
        draw(st.sampled_from([Outcome.MISS, Outcome.OK])),
        T0,
        detector=detector,
        attempt_id=draw(st.one_of(st.none(), st.sampled_from(ATTEMPTS))),
        scoring_config_id=draw(st.sampled_from(CONFIG_ORDER)),
    )


def attempt_observations() -> st.SearchStrategy[list[Observation]]:
    return st.lists(observations(), max_size=20)


def scored_pairs() -> st.SearchStrategy[list[tuple[str, str]]]:
    return st.lists(
        st.tuples(st.sampled_from(ATTEMPTS), st.sampled_from(CONFIG_ORDER)), max_size=12
    )
