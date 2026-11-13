"""Seed content: the calibration set and the baseline protocol, with their validators. Pure: no I/O.

Content ids are immutable (the repository refuses a changed text for an id), so an attempt keeps
the meaning it was recorded with. A malformed file or a failed rule raises `ContentInvalid` whose
message names a field and a short reason, never a value from the content.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal, cast

from nosolear.domain.attempts import AttemptStep
from nosolear.domain.calibration_items import (
    EPENTHESIS_KEY,
    CalibrationSpec,
    calibration_instruction,
)
from nosolear.domain.packs import CalibrationExtra
from nosolear.domain.taxonomy import Detector, Family, Taxonomy

__all__ = ["calibration_instruction"]

BASELINE_PROTOCOL_VERSION: Final = 1
TAKES_PER_WORD: Final = 2
MIN_KEY_TRIALS: Final = 5
MIN_CALIBRATION_WORDS: Final = 5
PASSAGE_WORDS: Final = (130, 170)
PASSAGE_SENTENCE_WORDS: Final = 25
RAPID_QUESTION_WORDS: Final = 12
WORD_LIST_WORDS: Final = 20
RAPID_QUESTIONS: Final = 5
RAPID_START_LIMIT_S: Final = 5
MIN_TOKENS_PER_KEY: Final = 3
MIN_STRESS_OCCURRENCES: Final = 2
CALIBRATION_FAMILIES: Final = frozenset({Family.SUB, Family.INS, Family.DEL})
_WORD_RE = re.compile(r"[\w']+")
_SECTION_ORDER: Final = (
    ("read_aloud", AttemptStep.READ_ALOUD),
    ("word_list", AttemptStep.WORD_LIST),
    ("free_talk", AttemptStep.SPEAK),
    ("rapid_questions", AttemptStep.QUICK_ANSWER),
    ("articulate", AttemptStep.ARTICULATE),
)


class ContentInvalid(ValueError):
    """Seed content that fails its format or a validation rule."""


class ContentKind(StrEnum):
    PROMPT = "prompt"
    PASSAGE_SENTENCE = "passage_sentence"
    MINIMAL_PAIR = "minimal_pair"
    DRILL_SENTENCE = "drill_sentence"
    STARTER = "starter"
    QUICK_QUESTION = "quick_question"
    CALIBRATION_WORD = "calibration_word"


UNSCRIPTED_KINDS: Final = frozenset({ContentKind.PROMPT, ContentKind.QUICK_QUESTION})


@dataclass(frozen=True, slots=True)
class ContentItem:
    id: str
    kind: ContentKind
    text: str
    target_keys: tuple[str, ...]
    source: Literal["seed", "coach"] = "seed"


@dataclass(frozen=True, slots=True)
class CalibrationWord:
    item_id: str
    error_key: str
    word: str
    respelling: str
    description: str


def calibration_word(
    error_key: str, word: str, respelling: str, description: str
) -> CalibrationWord:
    return CalibrationWord(f"cal:{error_key}:{word}", error_key, word, respelling, description)


@dataclass(frozen=True, slots=True)
class CalibrationSet:
    takes_per_word: int
    words: tuple[CalibrationWord, ...]

    def keys(self) -> tuple[str, ...]:
        """Each key once, in the order it first appears."""
        seen: dict[str, None] = {}
        for word in self.words:
            seen.setdefault(word.error_key, None)
        return tuple(seen)

    def words_for(self, key: str) -> tuple[CalibrationWord, ...]:
        return tuple(word for word in self.words if word.error_key == key)

    def word(self, item_id: str) -> CalibrationWord | None:
        return next((word for word in self.words if word.item_id == item_id), None)


@dataclass(frozen=True, slots=True)
class BaselineItem:
    item: ContentItem
    stand_in: str | None
    tokens: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class BaselineSection:
    name: str
    step: AttemptStep
    items: tuple[BaselineItem, ...]
    max_seconds: int | None
    start_limit_seconds: int | None


@dataclass(frozen=True, slots=True)
class BaselineProtocol:
    version: int
    sections: tuple[BaselineSection, ...]
    stress_pairs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SeedContent:
    calibration_set: CalibrationSet
    protocol: BaselineProtocol


def calibration_set(
    specs: Sequence[CalibrationSpec], *, extras: Sequence[CalibrationExtra] = ()
) -> CalibrationSet:
    """The specs in file order, with a pack's extra words appended to their key."""
    by_key: dict[str, list[CalibrationWord]] = {}
    descriptions: dict[str, str] = {}
    for spec in specs:
        descriptions.setdefault(spec.error_key, spec.description)
        for word, respelling in spec.words:
            by_key.setdefault(spec.error_key, []).append(
                calibration_word(spec.error_key, word, respelling, spec.description)
            )
    for extra in extras:
        if extra.respelling is None:
            raise ContentInvalid("calibration extra: a respelling is required")
        if extra.key not in descriptions:
            raise ContentInvalid("calibration extra: its key has no calibration spec")
        by_key.setdefault(extra.key, []).append(
            calibration_word(extra.key, extra.word, extra.respelling, descriptions[extra.key])
        )
    return CalibrationSet(
        takes_per_word=TAKES_PER_WORD,
        words=tuple(word for key in by_key for word in by_key[key]),
    )


def stand_in_text(word: CalibrationWord, *, deliberate: bool) -> str:
    """What a TTS control or an oracle says: the respelling for a deliberate take, else the word."""
    return word.respelling if deliberate else word.word


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def validate_calibration_set(
    cs: CalibrationSet, taxonomy: Taxonomy, *, min_words: int = MIN_CALIBRATION_WORDS
) -> None:
    problems: list[str] = []
    keys = cs.keys()
    for key in keys:
        field = f"calibration key {key}"
        if key not in taxonomy:
            problems.append(f"{field}: not a taxonomy key")
            continue
        definition = taxonomy.get(key)
        if definition.family not in CALIBRATION_FAMILIES:
            problems.append(f"{field}: must be a sound key")
        if not definition.detectors & {Detector.AZURE_PA, Detector.PHONE_PROBE}:
            problems.append(f"{field}: no detector can calibrate it")
        count = len(cs.words_for(key))
        if count < min_words or count * cs.takes_per_word < MIN_KEY_TRIALS:
            problems.append(f"{field}: too few calibration words")
    seen: set[str] = set()
    for word in cs.words:
        if word.item_id in seen:
            problems.append("calibration words: duplicate id")
        seen.add(word.item_id)
        if not word.word.strip() or not word.respelling.strip():
            problems.append("calibration words: blank word or respelling")
        elif word.word == word.respelling:
            problems.append("calibration words: a respelling must differ from its word")
    if problems:
        raise ContentInvalid("; ".join(problems))


def validate_baseline_protocol(p: BaselineProtocol, taxonomy: Taxonomy) -> None:
    problems: list[str] = []
    if p.version != BASELINE_PROTOCOL_VERSION:
        problems.append("protocol version: unsupported")
    if tuple((s.name, s.step) for s in p.sections) != _SECTION_ORDER:
        problems.append(
            "sections: must be read_aloud, word_list, free_talk, rapid_questions, articulate"
        )
    ids = [i.item.id for s in p.sections for i in s.items]
    if len(ids) != len(set(ids)):
        problems.append("item ids: must be unique")
    sections = {s.name: s for s in p.sections}
    if len(sections) == len(p.sections) and {"read_aloud", "word_list", "rapid_questions"} <= set(
        sections
    ):
        problems.extend(_passage_problems(sections["read_aloud"], p.stress_pairs, taxonomy))
        problems.extend(_word_list_problems(sections["word_list"]))
        problems.extend(_rapid_problems(sections["rapid_questions"]))
    for section in p.sections:
        for entry in section.items:
            if entry.item.kind in UNSCRIPTED_KINDS and not entry.stand_in:
                problems.append(f"item {entry.item.id}: an unscripted item needs a stand-in")
    if problems:
        raise ContentInvalid("; ".join(problems))


def _passage_problems(
    section: BaselineSection, stress_pairs: Sequence[str], taxonomy: Taxonomy
) -> list[str]:
    problems: list[str] = []
    passage = [entry.item.text for entry in section.items]
    total = sum(len(_words(text)) for text in passage)
    low, high = PASSAGE_WORDS
    if not low <= total <= high:
        problems.append(f"passage: must be {low} to {high} words")
    for text in passage:
        if len(_words(text)) > PASSAGE_SENTENCE_WORDS:
            problems.append(f"passage: a sentence has more than {PASSAGE_SENTENCE_WORDS} words")
    counts: dict[str, int] = {}
    for entry in section.items:
        sentence = set(_words(entry.item.text))
        for key, tokens in entry.tokens.items():
            counts[key] = counts.get(key, 0) + len(tokens)
            if any(token.lower() not in sentence for token in tokens):
                problems.append(f"item {entry.item.id}: an annotated word is not in its sentence")
    required = {d.key for d in taxonomy.defined() if d.family in (Family.SUB, Family.LOW)}
    for key in sorted(required | {EPENTHESIS_KEY}):
        if counts.get(key, 0) < MIN_TOKENS_PER_KEY:
            problems.append(f"passage: {key} needs at least {MIN_TOKENS_PER_KEY} annotated words")
    all_words = [word for text in passage for word in _words(text)]
    for pair in stress_pairs:
        if all_words.count(pair.lower()) < MIN_STRESS_OCCURRENCES:
            problems.append("passage: a stress pair word must occur at least twice")
    return problems


def _word_list_problems(section: BaselineSection) -> list[str]:
    count = sum(len(_words(entry.item.text)) for entry in section.items)
    if count != WORD_LIST_WORDS:
        return [f"word list: must hold exactly {WORD_LIST_WORDS} words"]
    return []


def _rapid_problems(section: BaselineSection) -> list[str]:
    problems: list[str] = []
    if len(section.items) != RAPID_QUESTIONS or section.start_limit_seconds != RAPID_START_LIMIT_S:
        problems.append(
            f"rapid questions: must be {RAPID_QUESTIONS} with a {RAPID_START_LIMIT_S} s start limit"
        )
    for entry in section.items:
        if len(_words(entry.item.text)) > RAPID_QUESTION_WORDS:
            problems.append(f"item {entry.item.id}: a quick question has more than 12 words")
    return problems


def seed_items(content: SeedContent) -> tuple[ContentItem, ...]:
    """Every calibration word and every protocol item, as content rows."""
    words = [
        ContentItem(
            word.item_id,
            ContentKind.CALIBRATION_WORD,
            word.word,
            (word.error_key,),
        )
        for word in content.calibration_set.words
    ]
    protocol = [entry.item for s in content.protocol.sections for entry in s.items]
    return tuple(words + protocol)


def _object(raw: object, field: str) -> Mapping[str, object]:
    if not isinstance(raw, Mapping):
        raise ContentInvalid(f"{field}: must be an object")
    return cast(Mapping[str, object], raw)


def _text(raw: Mapping[str, object], key: str, field: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise ContentInvalid(f"{field}.{key}: must be text")
    return value


def _optional_int(raw: Mapping[str, object], key: str, field: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentInvalid(f"{field}.{key}: must be a whole number")
    return value


def _list(raw: object, field: str) -> list[object]:
    if not isinstance(raw, list):
        raise ContentInvalid(f"{field}: must be a list")
    return cast(list[object], raw)


def _kind(value: str, field: str) -> ContentKind:
    try:
        return ContentKind(value)
    except ValueError:
        raise ContentInvalid(f"{field}.kind: unknown content kind") from None


def _item(raw: object, field: str) -> BaselineItem:
    obj = _object(raw, field)
    tokens_raw = _object(obj.get("tokens", {}), f"{field}.tokens")
    tokens: dict[str, tuple[str, ...]] = {}
    for key, words in tokens_raw.items():
        values = _list(words, f"{field}.tokens.{key}")
        if not all(isinstance(v, str) for v in values):
            raise ContentInvalid(f"{field}.tokens.{key}: must be a list of words")
        tokens[key] = tuple(cast(list[str], values))
    stand_in = obj.get("stand_in")
    if stand_in is not None and not isinstance(stand_in, str):
        raise ContentInvalid(f"{field}.stand_in: must be text")
    item = ContentItem(
        id=_text(obj, "id", field),
        kind=_kind(_text(obj, "kind", field), field),
        text=_text(obj, "text", field),
        target_keys=tuple(tokens),
    )
    return BaselineItem(item, stand_in, tokens)


def parse_baseline_protocol(raw: Mapping[str, object]) -> BaselineProtocol:
    """The protocol's JSON object, structure only. `validate_baseline_protocol` checks values."""
    version = raw.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ContentInvalid("protocol.version: must be a whole number")
    stress = _list(raw.get("stress_pairs", []), "protocol.stress_pairs")
    if not all(isinstance(w, str) for w in stress):
        raise ContentInvalid("protocol.stress_pairs: must be a list of words")
    sections: list[BaselineSection] = []
    for index, section_raw in enumerate(_list(raw.get("sections"), "protocol.sections")):
        field = f"protocol.sections[{index}]"
        obj = _object(section_raw, field)
        try:
            step = AttemptStep(_text(obj, "step", field))
        except ValueError:
            raise ContentInvalid(f"{field}.step: unknown attempt step") from None
        items = tuple(
            _item(entry, f"{field}.items[{n}]")
            for n, entry in enumerate(_list(obj.get("items"), f"{field}.items"))
        )
        sections.append(
            BaselineSection(
                name=_text(obj, "name", field),
                step=step,
                items=items,
                max_seconds=_optional_int(obj, "max_seconds", field),
                start_limit_seconds=_optional_int(obj, "start_limit_seconds", field),
            )
        )
    return BaselineProtocol(
        version=version,
        sections=tuple(sections),
        stress_pairs=tuple(cast(list[str], stress)),
    )
