"""Properties of `extract` over generated attempts, results and configs."""

import copy
from dataclasses import replace

from factories import PACK, TAX
from hypothesis import given
from strategies import extraction_items, provider_results, scoring_configs

from nosolear.domain.coach import TASK_FAMILIES, coach_task_for_step
from nosolear.domain.extraction.extract import ExtractionItem, ProviderResults, extract
from nosolear.domain.extraction.fluency import (
    FALSE_START,
    FILLER,
    LONG_PAUSE,
    SLOW_START,
    sentences,
)
from nosolear.domain.extraction.opportunities import tracked_keys
from nosolear.domain.scoring import ScoringConfig, enabled_keys
from nosolear.domain.taxonomy import Detector, Family

UNSCRIPTED = frozenset({"speak", "quick_answer", "articulate"})
FLUENCY_SENTENCE_KEYS = frozenset({FALSE_START, FILLER, LONG_PAUSE})
TRACKED = tracked_keys(TAX, PACK)


def _count(observations, key: str) -> int:
    return sum(o.error_key == key for o in observations)


@given(item=extraction_items(), results=provider_results(), config=scoring_configs())
def test_misses_never_exceed_opportunities(
    item: ExtractionItem, results: ProviderResults, config: ScoringConfig
) -> None:
    out = extract(item, results, config=config, pack=PACK, taxonomy=TAX)
    if item.step == "calibration":
        assert out == {}
        return
    asr = out.get(Detector.ASR_METRICS, ())
    assert _count(asr, SLOW_START) <= 1
    for detector, observations in out.items():
        for key in {o.error_key for o in observations}:
            family = TAX.get(key).family
            if family in (Family.STRUCTURE, Family.CLARITY):
                assert _count(observations, key) <= 1, (detector, key)


@given(item=extraction_items(), results=provider_results(), config=scoring_configs())
def test_sentence_keys_yield_one_observation_per_sentence(
    item: ExtractionItem, results: ProviderResults, config: ScoringConfig
) -> None:
    out = extract(item, results, config=config, pack=PACK, taxonomy=TAX)
    if item.step == "calibration" or results.transcript is None or item.step not in UNSCRIPTED:
        return
    sentence_count = len(sentences(results.transcript.words))
    asr_enabled = enabled_keys(config, Detector.ASR_METRICS, TRACKED, TAX)
    asr = out[Detector.ASR_METRICS]
    for key in FLUENCY_SENTENCE_KEYS & asr_enabled:
        assert _count(asr, key) == sentence_count


@given(item=extraction_items(), results=provider_results(), config=scoring_configs())
def test_grammar_keys_yield_one_observation_per_sentence(
    item: ExtractionItem, results: ProviderResults, config: ScoringConfig
) -> None:
    out = extract(item, results, config=config, pack=PACK, taxonomy=TAX)
    if item.step == "calibration" or results.transcript is None or results.coach is None:
        return
    task = coach_task_for_step(item.step)
    if task is None:
        assert out[Detector.COACH] == ()
        return
    sentence_count = len(sentences(results.transcript.words))
    coach_enabled = enabled_keys(config, Detector.COACH, TRACKED, TAX)
    for key in coach_enabled:
        definition = TAX.get(key)
        if definition.family is Family.GRAMMAR and definition.family in TASK_FAMILIES[task]:
            assert _count(out[Detector.COACH], key) == sentence_count


@given(item=extraction_items(), results=provider_results(), config=scoring_configs())
def test_extraction_is_deterministic(
    item: ExtractionItem, results: ProviderResults, config: ScoringConfig
) -> None:
    first = extract(item, results, config=config, pack=PACK, taxonomy=TAX)
    again = extract(
        copy.deepcopy(item), copy.deepcopy(results), config=config, pack=PACK, taxonomy=TAX
    )
    assert first == again
    shuffled = replace(PACK, hypotheses=tuple(reversed(PACK.hypotheses)))
    assert first == extract(item, results, config=config, pack=shuffled, taxonomy=TAX)


@given(item=extraction_items(), results=provider_results(), config=scoring_configs())
def test_provisional_matches_config_exactly(
    item: ExtractionItem, results: ProviderResults, config: ScoringConfig
) -> None:
    out = extract(item, results, config=config, pack=PACK, taxonomy=TAX)
    for detector, observations in out.items():
        for o in observations:
            rule = config.rule_for(o.detector, TAX.get(o.error_key))
            assert detector is o.detector
            assert rule is not None
            assert o.provisional == rule.provisional
            assert o.scoring_config_id == config.id
