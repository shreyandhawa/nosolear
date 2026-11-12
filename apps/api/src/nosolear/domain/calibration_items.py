"""Calibration recording items, built from the specs in `content/calibration/items.toml`."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from nosolear.domain.taxonomy import Taxonomy

EPENTHESIS_KEY = "sound.ins.epenthesis_sC"
DELIBERATE_TAKES = (1, 2)


@dataclass(frozen=True, slots=True)
class CalibrationSpec:
    error_key: str
    description: str
    words: tuple[tuple[str, str], ...]  # (word, respelling)


@dataclass(frozen=True, slots=True)
class CalibrationItem:
    id: str
    word: str
    error_key: str
    deliberate: bool
    instruction: str


def parse_calibration_specs(raw: Mapping[str, object]) -> tuple[CalibrationSpec, ...]:
    specs = raw.get("specs")
    if not isinstance(specs, list):
        raise ValueError("specs: must be a list")
    parsed: list[CalibrationSpec] = []
    for index, item in enumerate(cast(list[object], specs)):
        field = f"specs[{index}]"
        if not isinstance(item, Mapping):
            raise ValueError(f"{field}: must be a table")
        table = cast(Mapping[str, object], item)
        key, description, words = (
            table.get("error_key"),
            table.get("description"),
            table.get("words"),
        )
        if not isinstance(key, str) or not isinstance(description, str):
            raise ValueError(f"{field}: error_key and description must be text")
        if not isinstance(words, list):
            raise ValueError(f"{field}.words: must be a list")
        pairs: list[tuple[str, str]] = []
        for pair in cast(list[object], words):
            if isinstance(pair, list) and len(cast(list[object], pair)) == 2:
                word, respelling = cast(list[object], pair)
                if isinstance(word, str) and isinstance(respelling, str):
                    pairs.append((word, respelling))
                    continue
            raise ValueError(f"{field}.words: each entry must be [word, respelling]")
        parsed.append(CalibrationSpec(key, description, tuple(pairs)))
    return tuple(parsed)


def validate_calibration_specs(
    specs: Sequence[CalibrationSpec], taxonomy: Taxonomy
) -> tuple[str, ...]:
    found: list[str] = []
    seen_words: set[str] = set()
    for index, spec in enumerate(specs):
        field = f"specs[{index}]"
        if spec.error_key not in taxonomy:
            found.append(f"{field}.error_key: not a taxonomy key")
        if not spec.description.strip():
            found.append(f"{field}.description: must not be blank")
        if not spec.words:
            found.append(f"{field}.words: must not be empty")
        for word, respelling in spec.words:
            if not word.strip() or not respelling.strip():
                found.append(f"{field}.words: blank word or respelling")
            if word in seen_words:
                found.append(f"{field}.words: duplicate word")
            seen_words.add(word)
    return tuple(found)


def build_calibration_items(specs: Sequence[CalibrationSpec]) -> tuple[CalibrationItem, ...]:
    items: list[CalibrationItem] = []
    for spec in specs:
        for word, respelling in spec.words:
            items.append(
                CalibrationItem(
                    f"{word}__correct",
                    word,
                    spec.error_key,
                    False,
                    f'Say "{word}" as correctly as possible, in General American.',
                )
            )
            for take in DELIBERATE_TAKES:
                if spec.error_key == EPENTHESIS_KEY:
                    text = f'Say "{word}" with {spec.description}: "{respelling}"'
                else:
                    text = f'Say "{word}" with {spec.description}: sounds like "{respelling}"'
                items.append(
                    CalibrationItem(
                        f"{word}__err{take}",
                        word,
                        spec.error_key,
                        True,
                        f"{text} (take {take} of {len(DELIBERATE_TAKES)})",
                    )
                )
    return tuple(items)
