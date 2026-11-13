"""The calibration rule (ARCHITECTURE.md section 9.2), its planning and the calibrated config.

Pure: no I/O and no clock. A detector is enabled for a key only when the integer rule passes:
at least five error tokens and five TTS controls, five hits for every four errors, and no more
than one false alarm in five controls. Attempted-correct takes never enter the rule; they only
produce a warning.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Final

from nosolear.domain.content import CalibrationSet
from nosolear.domain.extraction.opportunities import Opportunity
from nosolear.domain.extraction.sounds import azure_opportunities, probe_opportunities
from nosolear.domain.scoring import (
    CALIBRATED_THRESHOLDS,
    V0_CONFIG,
    ConfigKind,
    KeyRule,
    ScoringConfig,
    Thresholds,
    TrialCounts,
)
from nosolear.domain.speech import PhoneProbeResult, PronunciationAssessment
from nosolear.domain.taxonomy import Detector, Taxonomy

WARNING_SHARE: Final = Fraction(1, 5)


class TrialKind(StrEnum):
    ERROR = "error"
    CONTROL = "control"


@dataclass(frozen=True, slots=True)
class Trial:
    """One clip judged by one detector for one key. Either an attempt or a TTS clip is its subject:
    an error trial is always an attempt, a control is a TTS clip or a correct take."""

    error_key: str
    detector: Detector
    kind: TrialKind
    attempt_id: str | None
    tts_hash: str | None
    flagged: bool | None

    def __post_init__(self) -> None:
        if (self.attempt_id is None) == (self.tts_hash is None):
            raise ValueError("a trial has exactly one subject: an attempt or a TTS clip")
        if self.kind is TrialKind.ERROR and self.attempt_id is None:
            raise ValueError("an error trial is an attempt")


def tally(trials: Iterable[Trial]) -> dict[tuple[Detector, str], TrialCounts]:
    totals: dict[tuple[Detector, str], dict[str, int]] = {}
    for item in trials:
        if item.flagged is None:
            continue
        row = totals.setdefault(
            (item.detector, item.error_key),
            {
                "errors": 0,
                "hits": 0,
                "controls": 0,
                "false_alarms": 0,
                "correct_takes": 0,
                "correct_flags": 0,
            },
        )
        if item.kind is TrialKind.ERROR:
            row["errors"] += 1
            row["hits"] += int(item.flagged)
        elif item.tts_hash is not None:
            row["controls"] += 1
            row["false_alarms"] += int(item.flagged)
        else:
            row["correct_takes"] += 1
            row["correct_flags"] += int(item.flagged)
    return {key: TrialCounts(**row) for key, row in totals.items()}


@dataclass(frozen=True, slots=True)
class CalibrationRule:
    min_errors: int = 5
    min_controls: int = 5
    min_hit_rate: Fraction = Fraction(4, 5)
    max_false_alarm_rate: Fraction = Fraction(1, 5)


DEFAULT_RULE: Final = CalibrationRule()


def covers(c: TrialCounts, rule: CalibrationRule = DEFAULT_RULE) -> bool:
    return c.errors >= rule.min_errors and c.controls >= rule.min_controls


def passes(c: TrialCounts, rule: CalibrationRule = DEFAULT_RULE) -> bool:
    return (
        covers(c, rule)
        and Fraction(c.hits, c.errors) >= rule.min_hit_rate
        and Fraction(c.false_alarms, c.controls) <= rule.max_false_alarm_rate
    )


@dataclass(frozen=True, slots=True)
class PairResult:
    detector: Detector
    error_key: str
    counts: TrialCounts
    covered: bool
    enabled: bool
    warning: str | None

    @property
    def hit_rate(self) -> float | None:
        return self.counts.hits / self.counts.errors if self.counts.errors else None

    @property
    def false_alarm_rate(self) -> float | None:
        return self.counts.false_alarms / self.counts.controls if self.counts.controls else None

    @property
    def correct_take_flag_rate(self) -> float | None:
        if not self.counts.correct_takes:
            return None
        return self.counts.correct_flags / self.counts.correct_takes


def _warning(c: TrialCounts) -> str:
    own = round(100 * c.correct_flags / c.correct_takes)
    controls = round(100 * c.false_alarms / c.controls) if c.controls else 0
    return (
        f"Your own correct takes were flagged {own}% of the time (TTS controls: {controls}%). "
        "This detector may count errors you didn't make on this key."
    )


def evaluate(
    trials: Iterable[Trial], rule: CalibrationRule = DEFAULT_RULE
) -> tuple[PairResult, ...]:
    results: list[PairResult] = []
    for (detector, error_key), c in tally(trials).items():
        enabled = passes(c, rule)
        warned = enabled and WARNING_SHARE * c.correct_takes < c.correct_flags
        results.append(
            PairResult(
                detector=detector,
                error_key=error_key,
                counts=c,
                covered=covers(c, rule),
                enabled=enabled,
                warning=_warning(c) if warned else None,
            )
        )
    return tuple(sorted(results, key=lambda r: (r.error_key, r.detector.value)))


def build_calibrated_config(
    *,
    config_id: str,
    run_id: str,
    results: Sequence[PairResult],
    base: ScoringConfig = V0_CONFIG,
) -> ScoringConfig:
    key_rules = tuple(
        KeyRule(
            detector=result.detector,
            error_key=result.error_key,
            enabled=result.enabled,
            thresholds=CALIBRATED_THRESHOLDS,
            counts=result.counts,
        )
        for result in results
        if result.covered
    )
    return ScoringConfig(
        id=config_id,
        kind=ConfigKind.CALIBRATED,
        calibration_run_id=run_id,
        thresholds=base.thresholds,
        family_rules=base.family_rules,
        key_rules=key_rules,
    )


def flagged(
    detector: Detector,
    error_key: str,
    result: PronunciationAssessment | PhoneProbeResult,
    *,
    reference_text: str,
    thresholds: Thresholds = CALIBRATED_THRESHOLDS,
) -> bool | None:
    """Whether this clip shows the key's error. None when the clip gives the key no opportunity."""
    keys = frozenset({error_key})
    opportunities: list[Opportunity]
    if detector is Detector.AZURE_PA and isinstance(result, PronunciationAssessment):
        opportunities = azure_opportunities(result, keys=keys, thresholds_for=lambda _: thresholds)
    elif detector is Detector.PHONE_PROBE and isinstance(result, PhoneProbeResult):
        opportunities = probe_opportunities(result, reference_text=reference_text, keys=keys)
    else:
        raise ValueError(f"{detector} does not judge this result")
    mine = [o for o in opportunities if o.error_key == error_key]
    if not mine:
        return None
    return any(o.missed for o in mine)


def calibratable_detectors(*, azure_nbest: bool, phone_probe_ready: bool) -> frozenset[Detector]:
    found: set[Detector] = set()
    if azure_nbest:
        found.add(Detector.AZURE_PA)
    if phone_probe_ready:
        found.add(Detector.PHONE_PROBE)
    return frozenset(found)


@dataclass(frozen=True, slots=True)
class PlannedToken:
    order: int
    item_id: str
    error_key: str
    word: str
    deliberate: bool
    take: int


@dataclass(frozen=True, slots=True)
class CalibrationPlan:
    detectors: Mapping[str, tuple[Detector, ...]]
    tokens: tuple[PlannedToken, ...]


def plan_calibration(
    cs: CalibrationSet,
    *,
    emphasis: Sequence[str],
    available: frozenset[Detector],
    taxonomy: Taxonomy,
) -> CalibrationPlan:
    """The pack's emphasis keys first, then the rest in file order. Per word: the correct take,
    then each deliberate take. A key with no available detector is dropped."""
    in_set = cs.keys()
    ordered: list[str] = []
    for key in emphasis:
        if key in in_set and key not in ordered:
            ordered.append(key)
    ordered.extend(key for key in in_set if key not in ordered)
    detectors: dict[str, tuple[Detector, ...]] = {}
    for key in ordered:
        allowed = taxonomy.get(key).detectors & available
        if allowed:
            detectors[key] = tuple(sorted(allowed, key=lambda d: d.value))
    tokens: list[PlannedToken] = []
    for key in detectors:
        for word in cs.words_for(key):
            takes = [(False, 1)] + [(True, take) for take in range(1, cs.takes_per_word + 1)]
            for deliberate, take in takes:
                tokens.append(
                    PlannedToken(
                        order=len(tokens) + 1,
                        item_id=word.item_id,
                        error_key=key,
                        word=word.word,
                        deliberate=deliberate,
                        take=take,
                    )
                )
    return CalibrationPlan(detectors=detectors, tokens=tuple(tokens))
