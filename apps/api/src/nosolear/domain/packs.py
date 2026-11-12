"""Language packs: weak first-language guesses that never change the taxonomy.

A pack gives some keys a hypothesis prior, names the keys to calibrate first and may add extra
calibration words. `parse_pack` checks structure and types; `validate_pack` checks values against
the taxonomy. Error messages name a field and a short reason, never the offending value.
"""

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from nosolear.domain.estimates import DEFAULT_PRIOR, HYPOTHESIS_PRIOR, Prior
from nosolear.domain.taxonomy import Taxonomy

PACK_ID_PATTERN = r"^[a-z0-9_]+$"
MAX_PRIOR_MASS = 20.0  # a0 + b0 above this is "out of range": one baseline must outweigh any prior
MAX_WORD_LENGTH = 40

_ID_RE = re.compile(PACK_ID_PATTERN)


class PackError(ValueError):
    """Malformed structure or failed validation; the message lists every problem."""


@dataclass(frozen=True, slots=True)
class PackHypothesis:
    key: str
    reason: str
    prior: Prior


@dataclass(frozen=True, slots=True)
class CalibrationExtra:
    key: str
    word: str
    respelling: str | None


@dataclass(frozen=True, slots=True)
class LanguagePack:
    id: str
    name: str
    description: str
    default_prior: Prior
    hypotheses: tuple[PackHypothesis, ...]
    calibration_emphasis: tuple[str, ...]
    calibration_extras: tuple[CalibrationExtra, ...]

    def prior_for(self, key: str) -> Prior:
        for hypothesis in self.hypotheses:
            if hypothesis.key == key:
                return hypothesis.prior
        return self.default_prior


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _mapping(value: object, field: str, problems: list[str]) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    problems.append(f"{field}: must be a table")
    return None


def _string(raw: Mapping[str, object], key: str, field: str, problems: list[str]) -> str:
    value = raw.get(key)
    if isinstance(value, str):
        return value
    problems.append(f"{field}: must be text" if key in raw else f"{field}: missing")
    return ""


def _prior(value: object, field: str, default: Prior, problems: list[str]) -> Prior:
    if value is None:
        return default
    table = _mapping(value, field, problems)
    if table is None:
        return default
    numbers: dict[str, float] = {}
    for name, fallback in (("a0", default.a0), ("b0", default.b0)):
        item = table.get(name, fallback)
        if _is_number(item):
            numbers[name] = float(item)  # type: ignore[arg-type]
        else:
            problems.append(f"{field}.{name}: must be a number")
            numbers[name] = fallback
    return Prior(numbers["a0"], numbers["b0"])


def _list(value: object, field: str, problems: list[str]) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return cast(list[object], value)
    problems.append(f"{field}: must be a list")
    return []


def parse_pack(raw: Mapping[str, object]) -> LanguagePack:
    problems: list[str] = []
    pack_id = _string(raw, "id", "id", problems)
    name = _string(raw, "name", "name", problems)
    description = _string(raw, "description", "description", problems)
    default_prior = _prior(raw.get("default_prior"), "default_prior", DEFAULT_PRIOR, problems)

    hypotheses: list[PackHypothesis] = []
    for index, item in enumerate(_list(raw.get("hypotheses"), "hypotheses", problems)):
        field = f"hypotheses[{index}]"
        table = _mapping(item, field, problems)
        if table is None:
            continue
        hypotheses.append(
            PackHypothesis(
                key=_string(table, "key", f"{field}.key", problems),
                reason=_string(table, "reason", f"{field}.reason", problems),
                prior=_prior(table.get("prior"), f"{field}.prior", HYPOTHESIS_PRIOR, problems),
            )
        )

    emphasis: list[str] = []
    extras: list[CalibrationExtra] = []
    calibration = _mapping(raw.get("calibration"), "calibration", problems)
    if calibration is not None:
        for index, item in enumerate(
            _list(calibration.get("emphasis"), "calibration.emphasis", problems)
        ):
            if isinstance(item, str):
                emphasis.append(item)
            else:
                problems.append(f"calibration.emphasis[{index}]: must be text")
        for index, item in enumerate(
            _list(calibration.get("extras"), "calibration.extras", problems)
        ):
            field = f"calibration.extras[{index}]"
            table = _mapping(item, field, problems)
            if table is None:
                continue
            respelling = table.get("respelling")
            if respelling is not None and not isinstance(respelling, str):
                problems.append(f"{field}.respelling: must be text")
                respelling = None
            extras.append(
                CalibrationExtra(
                    key=_string(table, "key", f"{field}.key", problems),
                    word=_string(table, "word", f"{field}.word", problems),
                    respelling=respelling,
                )
            )

    if problems:
        raise PackError("; ".join(problems))
    return LanguagePack(
        id=pack_id,
        name=name,
        description=description,
        default_prior=default_prior,
        hypotheses=tuple(hypotheses),
        calibration_emphasis=tuple(emphasis),
        calibration_extras=tuple(extras),
    )


def _prior_problems(prior: Prior, field: str) -> list[str]:
    if not (math.isfinite(prior.a0) and math.isfinite(prior.b0)):
        return [f"{field}: must be finite"]
    found: list[str] = []
    if prior.a0 <= 0:
        found.append(f"{field}.a0: must be above 0")
    if prior.b0 <= 0:
        found.append(f"{field}.b0: must be above 0")
    if prior.a0 + prior.b0 > MAX_PRIOR_MASS:
        found.append(f"{field}: a0 + b0 must be at most {MAX_PRIOR_MASS:g}")
    return found


def _bad_word(word: str) -> str | None:
    if not word.strip():
        return "must not be blank"
    if len(word) > MAX_WORD_LENGTH:
        return f"must be at most {MAX_WORD_LENGTH} characters"
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in word):
        return "must not contain control characters"
    return None


def validate_pack(pack: LanguagePack, taxonomy: Taxonomy) -> tuple[str, ...]:
    found: list[str] = []
    if not _ID_RE.fullmatch(pack.id):
        found.append("id: must be lowercase letters, digits and underscores")
    if not pack.name.strip():
        found.append("name: must not be blank")
    if not pack.description.strip():
        found.append("description: must not be blank")
    found.extend(_prior_problems(pack.default_prior, "default_prior"))

    seen: set[str] = set()
    for index, hypothesis in enumerate(pack.hypotheses):
        field = f"hypotheses[{index}]"
        if hypothesis.key not in taxonomy:
            found.append(f"{field}.key: not a taxonomy key")
        if hypothesis.key in seen:
            found.append(f"{field}.key: duplicate")
        seen.add(hypothesis.key)
        if not hypothesis.reason.strip():
            found.append(f"{field}.reason: must not be blank")
        found.extend(_prior_problems(hypothesis.prior, f"{field}.prior"))

    seen_emphasis: set[str] = set()
    for index, key in enumerate(pack.calibration_emphasis):
        field = f"calibration.emphasis[{index}]"
        if key not in taxonomy:
            found.append(f"{field}: not a taxonomy key")
        if key in seen_emphasis:
            found.append(f"{field}: duplicate")
        seen_emphasis.add(key)

    for index, extra in enumerate(pack.calibration_extras):
        field = f"calibration.extras[{index}]"
        if extra.key not in taxonomy:
            found.append(f"{field}.key: not a taxonomy key")
        reason = _bad_word(extra.word)
        if reason:
            found.append(f"{field}.word: {reason}")
        if extra.respelling is not None and (reason := _bad_word(extra.respelling)):
            found.append(f"{field}.respelling: {reason}")
    return tuple(found)
