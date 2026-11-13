"""Hypothesis strategies for scoring configs and observations. Import from `strategies`."""

from factories import (
    T0,
    TAX,
    coach_analysis,
    finding,
    mk,
    pa_phone,
    pa_result,
    pa_word,
    probe_result,
    transcript,
)
from hypothesis import strategies as st

from nosolear.domain.coach import CoachAnalysis, CoachFinding
from nosolear.domain.extraction.extract import ExtractionItem, ProviderResults
from nosolear.domain.observations import Observation, Outcome
from nosolear.domain.phones import AZURE_PHONES
from nosolear.domain.scoring import (
    ConfigKind,
    FamilyRule,
    KeyRule,
    ScoringConfig,
    Thresholds,
    TrialCounts,
)
from nosolear.domain.speech import (
    PhonemeAssessment,
    PhoneProbeResult,
    PronunciationAssessment,
    Transcript,
    WordAssessment,
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


_PHONES = sorted(AZURE_PHONES)
_ERROR_TYPES = ["None", "Mispronunciation", "Omission", "Insertion"]
_PROSODY = ["UnexpectedBreak", "MissingBreak", "Monotone"]


@st.composite
def _phone_assessments(draw: st.DrawFn) -> PhonemeAssessment:
    phone = draw(st.sampled_from(_PHONES))
    accuracy = draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False))
    nbest = draw(
        st.lists(
            st.tuples(
                st.sampled_from(_PHONES),
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
            ),
            max_size=3,
        )
    )
    return pa_phone(phone, accuracy, nbest)


@st.composite
def _word_assessments(draw: st.DrawFn) -> WordAssessment:
    phones = draw(st.lists(_phone_assessments(), max_size=4))
    return pa_word(
        "w",
        phones,
        error_type=draw(st.sampled_from(_ERROR_TYPES)),
        prosody=draw(st.lists(st.sampled_from(_PROSODY), max_size=2)),
    )


@st.composite
def pronunciation_results(
    draw: st.DrawFn, has_nbest: bool | None = None, has_prosody: bool | None = None
) -> PronunciationAssessment:
    words = draw(st.lists(_word_assessments(), max_size=5))
    nbest = draw(st.booleans()) if has_nbest is None else has_nbest
    prosody = draw(st.booleans()) if has_prosody is None else has_prosody
    return pa_result(words, has_nbest=nbest, has_prosody=prosody)


@st.composite
def probe_results(draw: st.DrawFn) -> PhoneProbeResult:
    expected = draw(
        st.lists(st.lists(st.sampled_from(_PHONES), min_size=1, max_size=4), min_size=0, max_size=3)
    )
    heard = draw(st.lists(st.sampled_from(_PHONES), max_size=8))
    return probe_result(None, expected, heard)


_WORDS = ["I", "um", "went", "home.", "we", "think", "uh", "yesterday?", "fun!", "the", "Well,"]
_QUOTES = [None, "I went", "went home", "um", "the market", "I think"]
_STEPS = [
    "speak",
    "read_aloud",
    "word_list",
    "quick_answer",
    "articulate",
    "retell",
    "drill",
    "shadow",
    "calibration",
]


@st.composite
def transcripts(draw: st.DrawFn) -> Transcript:
    items = draw(
        st.lists(
            st.tuples(
                st.sampled_from(_WORDS),
                st.integers(min_value=0, max_value=2500),
                st.integers(min_value=0, max_value=800),
            ),
            max_size=12,
        )
    )
    words: list[tuple[str, int, int]] = []
    now = 0
    for text, gap, length in items:
        start = now + gap
        words.append((text, start, start + length))
        now = start + length
    return transcript(*words, fillers_kept=draw(st.booleans()))


@st.composite
def coach_analyses(draw: st.DrawFn) -> CoachAnalysis:
    keys = [*_KEYS, "grammar.x'); DROP TABLE observations;--"]
    findings: list[CoachFinding] = draw(
        st.lists(
            st.tuples(st.sampled_from(keys), st.sampled_from(_QUOTES)),
            max_size=6,
        ).map(lambda picked: [finding(key, quote) for key, quote in picked])
    )
    return coach_analysis(findings)


@st.composite
def extraction_items(draw: st.DrawFn) -> ExtractionItem:
    return ExtractionItem(
        attempt_id="a1",
        step=draw(st.sampled_from(_STEPS)),
        scripted=draw(st.booleans()),
        reference_text=draw(st.one_of(st.none(), st.just("Seven vans."))),
        observed_at=T0,
    )


@st.composite
def provider_results(draw: st.DrawFn) -> ProviderResults:
    return ProviderResults(
        pronunciation=draw(st.one_of(st.none(), pronunciation_results())),
        transcript=draw(st.one_of(st.none(), transcripts())),
        phone_probe=draw(st.one_of(st.none(), probe_results())),
        coach=draw(st.one_of(st.none(), coach_analyses())),
    )
