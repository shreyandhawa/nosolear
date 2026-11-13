"""Scoring configs: which detector may score which key, and with what thresholds.

Pure and deterministic: no I/O. A config is either the shipped `v0` rules or a calibrated
config written by a calibration run.
"""

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from nosolear.domain.taxonomy import Detector, Family, KeyDefinition, Taxonomy

if TYPE_CHECKING:
    from nosolear.domain.observations import Observation

V0_CONFIG_ID = "v0"
RULES_SCHEMA = 1


class ConfigKind(StrEnum):
    V0 = "v0"
    CALIBRATED = "calibrated"


class ScoringConfigInvalid(ValueError):
    """Raised when a scoring config or its serialized rules break an invariant."""


@dataclass(frozen=True, slots=True)
class Thresholds:
    nbest_margin: float
    low_accuracy: float
    slow_start_ms: int
    long_pause_ms: int


V0_THRESHOLDS = Thresholds(
    nbest_margin=30.0, low_accuracy=40.0, slow_start_ms=3000, long_pause_ms=2000
)
CALIBRATED_THRESHOLDS = Thresholds(
    nbest_margin=15.0, low_accuracy=60.0, slow_start_ms=3000, long_pause_ms=2000
)

SOUND_FAMILIES: frozenset[Family] = frozenset(
    {Family.SUB, Family.LOW, Family.INS, Family.DEL, Family.PROSODY}
)


@dataclass(frozen=True, slots=True)
class FamilyRule:
    detector: Detector
    family: Family
    enabled: bool
    provisional: bool


@dataclass(frozen=True, slots=True)
class TrialCounts:
    errors: int
    hits: int
    controls: int
    false_alarms: int
    correct_takes: int
    correct_flags: int


@dataclass(frozen=True, slots=True)
class KeyRule:
    detector: Detector
    error_key: str
    enabled: bool
    thresholds: Thresholds
    counts: TrialCounts


@dataclass(frozen=True, slots=True)
class ScoringRule:
    provisional: bool
    thresholds: Thresholds


@dataclass(frozen=True, slots=True)
class ScoringConfig:
    id: str
    kind: ConfigKind
    calibration_run_id: str | None
    thresholds: Thresholds
    family_rules: tuple[FamilyRule, ...]
    key_rules: tuple[KeyRule, ...]

    def __post_init__(self) -> None:
        if (self.kind is ConfigKind.V0) != (self.calibration_run_id is None):
            raise ScoringConfigInvalid("kind v0 must have no calibration run, and only v0 may")
        family_keys = [(r.detector, r.family) for r in self.family_rules]
        if len(set(family_keys)) != len(family_keys):
            raise ScoringConfigInvalid("duplicate family rule")
        key_keys = [(r.error_key, r.detector) for r in self.key_rules]
        if len(set(key_keys)) != len(key_keys):
            raise ScoringConfigInvalid("duplicate key rule")

    def rule_for(self, detector: Detector, definition: KeyDefinition) -> ScoringRule | None:
        """The rule that scores this key from this detector, or None when it is not scored."""
        if detector not in definition.detectors:
            return None
        for key_rule in self.key_rules:
            if key_rule.error_key == definition.key and key_rule.detector == detector:
                if key_rule.enabled:
                    return ScoringRule(False, key_rule.thresholds)
                return None
        for family_rule in self.family_rules:
            if family_rule.detector == detector and family_rule.family == definition.family:
                if family_rule.enabled:
                    return ScoringRule(family_rule.provisional, self.thresholds)
                return None
        return None


V0_FAMILY_RULES: tuple[FamilyRule, ...] = (
    FamilyRule(Detector.ASR_METRICS, Family.FLUENCY, True, False),
    FamilyRule(Detector.AZURE_PA, Family.PROSODY, True, True),
    FamilyRule(Detector.AZURE_PA, Family.LOW, True, True),
    FamilyRule(Detector.AZURE_PA, Family.SUB, True, True),
    FamilyRule(Detector.COACH, Family.CLARITY, True, False),
    FamilyRule(Detector.COACH, Family.GRAMMAR, True, False),
    FamilyRule(Detector.COACH, Family.STRUCTURE, True, False),
    FamilyRule(Detector.PHONE_PROBE, Family.DEL, False, True),
    FamilyRule(Detector.PHONE_PROBE, Family.INS, False, True),
    FamilyRule(Detector.PHONE_PROBE, Family.SUB, False, True),
)

V0_CONFIG = ScoringConfig(
    id=V0_CONFIG_ID,
    kind=ConfigKind.V0,
    calibration_run_id=None,
    thresholds=V0_THRESHOLDS,
    family_rules=V0_FAMILY_RULES,
    key_rules=(),
)


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _thresholds_json(t: Thresholds) -> dict[str, object]:
    return {
        "nbest_margin": t.nbest_margin,
        "low_accuracy": t.low_accuracy,
        "slow_start_ms": t.slow_start_ms,
        "long_pause_ms": t.long_pause_ms,
    }


def _counts_json(c: TrialCounts) -> dict[str, object]:
    return {
        "errors": c.errors,
        "hits": c.hits,
        "controls": c.controls,
        "false_alarms": c.false_alarms,
        "correct_takes": c.correct_takes,
        "correct_flags": c.correct_flags,
    }


def rules_to_json(config: ScoringConfig) -> dict[str, object]:
    family_rules = sorted(config.family_rules, key=lambda r: (r.detector, r.family))
    key_rules = sorted(config.key_rules, key=lambda r: (r.error_key, r.detector))
    return {
        "schema": RULES_SCHEMA,
        "thresholds": _thresholds_json(config.thresholds),
        "family_rules": [
            {
                "detector": r.detector.value,
                "family": r.family.value,
                "enabled": r.enabled,
                "provisional": r.provisional,
            }
            for r in family_rules
        ],
        "key_rules": [
            {
                "error_key": r.error_key,
                "detector": r.detector.value,
                "enabled": r.enabled,
                "thresholds": _thresholds_json(r.thresholds),
                "counts": _counts_json(r.counts),
            }
            for r in key_rules
        ],
    }


def _object(raw: object) -> Mapping[str, object]:
    if not isinstance(raw, Mapping):
        raise ScoringConfigInvalid("expected an object")
    return cast(Mapping[str, object], raw)


def _list(raw: object) -> list[object]:
    if not isinstance(raw, list):
        raise ScoringConfigInvalid("expected a list")
    return cast(list[object], raw)


def _finite(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ScoringConfigInvalid(f"expected a number, got {value!r}")
    if not math.isfinite(value):
        raise ScoringConfigInvalid(f"expected a finite number, got {value!r}")
    return float(value)


def _whole(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScoringConfigInvalid(f"expected an integer, got {value!r}")
    return value


def _count(value: object) -> int:
    number = _whole(value)
    if number < 0:
        raise ScoringConfigInvalid(f"expected a non-negative count, got {number}")
    return number


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise ScoringConfigInvalid(f"expected a boolean, got {value!r}")
    return value


def _thresholds_from(raw: object) -> Thresholds:
    obj = _object(raw)
    return Thresholds(
        nbest_margin=_finite(obj["nbest_margin"]),
        low_accuracy=_finite(obj["low_accuracy"]),
        slow_start_ms=_whole(obj["slow_start_ms"]),
        long_pause_ms=_whole(obj["long_pause_ms"]),
    )


def _counts_from(raw: object) -> TrialCounts:
    obj = _object(raw)
    counts = TrialCounts(
        errors=_count(obj["errors"]),
        hits=_count(obj["hits"]),
        controls=_count(obj["controls"]),
        false_alarms=_count(obj["false_alarms"]),
        correct_takes=_count(obj["correct_takes"]),
        correct_flags=_count(obj["correct_flags"]),
    )
    if counts.hits > counts.errors:
        raise ScoringConfigInvalid("hits cannot exceed errors")
    if counts.false_alarms > counts.controls:
        raise ScoringConfigInvalid("false alarms cannot exceed controls")
    if counts.correct_flags > counts.correct_takes:
        raise ScoringConfigInvalid("correct flags cannot exceed correct takes")
    return counts


def _family_rule_from(raw: object) -> FamilyRule:
    obj = _object(raw)
    return FamilyRule(
        detector=Detector(_str(obj["detector"])),
        family=Family(_str(obj["family"])),
        enabled=_bool(obj["enabled"]),
        provisional=_bool(obj["provisional"]),
    )


def _key_rule_from(raw: object, taxonomy: Taxonomy) -> KeyRule:
    obj = _object(raw)
    error_key = _str(obj["error_key"])
    if error_key not in taxonomy:
        raise ScoringConfigInvalid(f"unknown error key {error_key!r}")
    detector = Detector(_str(obj["detector"]))
    if detector not in taxonomy.get(error_key).detectors:
        raise ScoringConfigInvalid(f"{detector} may not score {error_key}")
    return KeyRule(
        detector=detector,
        error_key=error_key,
        enabled=_bool(obj["enabled"]),
        thresholds=_thresholds_from(obj["thresholds"]),
        counts=_counts_from(obj["counts"]),
    )


def _str(value: object) -> str:
    if not isinstance(value, str):
        raise ScoringConfigInvalid(f"expected a string, got {value!r}")
    return value


def rules_from_json(
    *,
    config_id: str,
    kind: ConfigKind,
    calibration_run_id: str | None,
    rules: Mapping[str, object],
    taxonomy: Taxonomy,
) -> ScoringConfig:
    schema = rules.get("schema")
    if isinstance(schema, bool) or schema != RULES_SCHEMA:
        raise ScoringConfigInvalid(f"unsupported rules schema {schema!r}")
    try:
        thresholds = _thresholds_from(rules["thresholds"])
        family_rules = tuple(_family_rule_from(raw) for raw in _list(rules["family_rules"]))
        key_rules = tuple(_key_rule_from(raw, taxonomy) for raw in _list(rules["key_rules"]))
    except ScoringConfigInvalid:
        raise
    except (KeyError, ValueError) as exc:
        raise ScoringConfigInvalid(f"malformed scoring rules: {exc}") from exc
    return ScoringConfig(
        id=config_id,
        kind=kind,
        calibration_run_id=calibration_run_id,
        thresholds=thresholds,
        family_rules=tuple(sorted(family_rules, key=lambda r: (r.detector, r.family))),
        key_rules=tuple(sorted(key_rules, key=lambda r: (r.error_key, r.detector))),
    )


def enabled_keys(
    config: ScoringConfig, detector: Detector, keys: Iterable[str], taxonomy: Taxonomy
) -> frozenset[str]:
    return frozenset(
        key for key in keys if config.rule_for(detector, taxonomy.get(key)) is not None
    )


def current_observations(
    observations: Iterable[Observation],
    *,
    scored: Iterable[tuple[str, str]],
    config_order: Sequence[str],
) -> list[Observation]:
    """Keep, per attempt, only the observations of the newest config that scored it.

    An attempt with no scored pair keeps all of its observations, as does an observation with
    no attempt. Input order is preserved.
    """
    rank = {config_id: position for position, config_id in enumerate(config_order)}
    newest: dict[str, str] = {}
    for attempt_id, config_id in scored:
        held = newest.get(attempt_id)
        if held is None or rank[config_id] > rank[held]:
            newest[attempt_id] = config_id
    return [
        obs
        for obs in observations
        if obs.attempt_id is None
        or obs.attempt_id not in newest
        or obs.scoring_config_id == newest[obs.attempt_id]
    ]
