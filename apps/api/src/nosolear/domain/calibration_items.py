"""Calibration recording items, built from the specs in `content/calibration/items.toml`."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from nosolear.domain.taxonomy import Taxonomy

EPENTHESIS_KEY = "sound.ins.epenthesis_sC"
DELIBERATE_TAKES = (1, 2)


class CalibrationWordLike(Protocol):
    """One calibration word and its copy: what `calibration_instruction` reads."""

    @property
    def error_key(self) -> str: ...

    @property
    def word(self) -> str: ...

    @property
    def respelling(self) -> str: ...

    @property
    def description(self) -> str: ...


@dataclass(frozen=True, slots=True)
class _Pair:
    error_key: str
    word: str
    respelling: str
    description: str


def calibration_instruction(
    item: CalibrationWordLike, *, deliberate: bool, take: int, takes: int
) -> str:
    """The on-screen copy for one take. The shipped and seeded calibration words share it."""
    word = item.word
    if not deliberate:
        return f'Say "{word}" as correctly as possible, in General American.'
    if item.error_key == EPENTHESIS_KEY:
        text = f'Say "{word}" with {item.description}: "{item.respelling}"'
    else:
        text = f'Say "{word}" with {item.description}: sounds like "{item.respelling}"'
    return f"{text} (take {take} of {takes})"


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
            pair = _Pair(spec.error_key, word, respelling, spec.description)
            items.append(
                CalibrationItem(
                    f"{word}__correct",
                    word,
                    spec.error_key,
                    False,
                    calibration_instruction(pair, deliberate=False, take=0, takes=0),
                )
            )
            for take in DELIBERATE_TAKES:
                items.append(
                    CalibrationItem(
                        f"{word}__err{take}",
                        word,
                        spec.error_key,
                        True,
                        calibration_instruction(
                            pair, deliberate=True, take=take, takes=len(DELIBERATE_TAKES)
                        ),
                    )
                )
    return tuple(items)
