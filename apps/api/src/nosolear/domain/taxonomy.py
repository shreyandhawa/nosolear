"""The error taxonomy: every key the app can score, with its impact, drills and detectors.

Phone symbols follow Azure's en-US IPA set. Changing any of them is a taxonomy version bump.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

TAXONOMY_VERSION = 1


class Skill(StrEnum):
    SOUNDS = "sounds"
    ON_THE_SPOT = "on_the_spot"
    ARTICULATE = "articulate"


class Family(StrEnum):
    SUB = "sound.sub"
    LOW = "sound.low"
    INS = "sound.ins"
    DEL = "sound.del"
    PROSODY = "prosody"
    FLUENCY = "fluency"
    GRAMMAR = "grammar"
    STRUCTURE = "structure"
    CLARITY = "clarity"


class Detector(StrEnum):
    AZURE_PA = "azure_pa"
    PHONE_PROBE = "phone_probe"
    ASR_METRICS = "asr_metrics"
    COACH = "coach"


_FAMILY_SKILL: dict[Family, Skill] = {
    Family.SUB: Skill.SOUNDS,
    Family.LOW: Skill.SOUNDS,
    Family.INS: Skill.SOUNDS,
    Family.DEL: Skill.SOUNDS,
    Family.PROSODY: Skill.SOUNDS,
    Family.FLUENCY: Skill.ON_THE_SPOT,
    Family.GRAMMAR: Skill.ON_THE_SPOT,
    Family.STRUCTURE: Skill.ARTICULATE,
    Family.CLARITY: Skill.ARTICULATE,
}


@dataclass(frozen=True, slots=True)
class KeyDefinition:
    key: str
    family: Family
    skill: Skill
    impact: int
    drill_family: str
    detectors: frozenset[Detector]
    hypothesis: bool
    description: str


class UnknownErrorKey(ValueError):
    """Raised for a key that is neither listed nor a well-formed dynamic sound key."""


def _is_phone(part: str) -> bool:
    return bool(part) and not any(ch.isspace() for ch in part)


def _sub_description(expected: str, produced: str) -> str:
    return f"/{expected}/ said as /{produced}/"


def _low_description(phone: str) -> str:
    return f"/{phone}/ unclear"


def _definition(
    key: str,
    family: Family,
    impact: int,
    drill_family: str,
    detectors: Iterable[Detector],
    hypothesis: bool,
    description: str,
) -> KeyDefinition:
    return KeyDefinition(
        key=key,
        family=family,
        skill=_FAMILY_SKILL[family],
        impact=impact,
        drill_family=drill_family,
        detectors=frozenset(detectors),
        hypothesis=hypothesis,
        description=description,
    )


_SUB_DETECTORS = (Detector.AZURE_PA, Detector.PHONE_PROBE)
_LOW_DETECTORS = (Detector.AZURE_PA,)


def _sub(expected: str, produced: str, impact: int, hypothesis: bool = True) -> KeyDefinition:
    return _definition(
        f"{Family.SUB}.{expected}.{produced}",
        Family.SUB,
        impact,
        "minimal_pairs",
        _SUB_DETECTORS,
        hypothesis,
        _sub_description(expected, produced),
    )


def _low(phone: str, impact: int) -> KeyDefinition:
    return _definition(
        f"{Family.LOW}.{phone}",
        Family.LOW,
        impact,
        "sound_practice",
        _LOW_DETECTORS,
        True,
        _low_description(phone),
    )


_AZURE = (Detector.AZURE_PA,)
_PROBE = (Detector.PHONE_PROBE,)
_ASR = (Detector.ASR_METRICS,)
_COACH = (Detector.COACH,)

_EXPLICIT: tuple[KeyDefinition, ...] = (
    _sub("v", "w", 3),
    _sub("w", "v", 3),
    _sub("f", "p", 3),
    _sub("ʃ", "s", 3),
    _sub("s", "ʃ", 3),
    _sub("θ", "t", 2),
    _sub("z", "dʒ", 2),
    _sub("z", "s", 2),
    _sub("ð", "d", 1),
    _sub("ʒ", "dʒ", 1),
    _sub("i", "ɪ", 3),
    _sub("ɪ", "i", 3),
    _sub("æ", "ɛ", 3),
    _sub("ʌ", "ɑ", 2),
    _low("t", 2),
    _low("d", 2),
    _low("ɹ", 2),
    _low("ɝ", 2),
    _low("θ", 1),
    _low("ð", 1),
    _definition(
        "sound.ins.epenthesis_sC",
        Family.INS,
        2,
        "cluster_practice",
        _PROBE,
        True,
        "Extra vowel added before an s-cluster, like 'istop' for 'stop'",
    ),
    _definition(
        "sound.del.final_cluster",
        Family.DEL,
        2,
        "cluster_practice",
        (Detector.PHONE_PROBE, Detector.AZURE_PA),
        False,
        "Last consonant dropped from a word-final cluster, like 'tes' for 'test'",
    ),
    _definition(
        "prosody.word_stress",
        Family.PROSODY,
        3,
        "stress_practice",
        (),
        True,
        "Stress on the wrong syllable of a word",
    ),
    _definition(
        "prosody.unexpected_break",
        Family.PROSODY,
        2,
        "rhythm_practice",
        _AZURE,
        True,
        "Pausing in the middle of a phrase where there is no break",
    ),
    _definition(
        "prosody.monotone",
        Family.PROSODY,
        2,
        "rhythm_practice",
        _AZURE,
        True,
        "Pitch stays flat instead of rising and falling",
    ),
    _definition(
        "prosody.missing_break",
        Family.PROSODY,
        1,
        "rhythm_practice",
        _AZURE,
        False,
        "Running on without a pause where one is expected",
    ),
    _definition(
        "fluency.slow_start",
        Family.FLUENCY,
        3,
        "rapid_questions",
        _ASR,
        False,
        "Long wait before starting to answer",
    ),
    _definition(
        "fluency.filler",
        Family.FLUENCY,
        2,
        "rapid_questions",
        _ASR,
        False,
        "Filler words like 'um' and 'uh'",
    ),
    _definition(
        "fluency.long_pause",
        Family.FLUENCY,
        2,
        "rapid_questions",
        _ASR,
        False,
        "Long pause in the middle of an answer",
    ),
    _definition(
        "fluency.false_start",
        Family.FLUENCY,
        1,
        "rapid_questions",
        _ASR,
        False,
        "Starting a sentence, then dropping it and starting again",
    ),
    _definition(
        "grammar.verb_tense",
        Family.GRAMMAR,
        3,
        "grammar_rewrite",
        _COACH,
        False,
        "Wrong verb tense, like 'I go yesterday'",
    ),
    _definition(
        "grammar.article",
        Family.GRAMMAR,
        2,
        "grammar_rewrite",
        _COACH,
        True,
        "Missing or wrong a, an or the",
    ),
    _definition(
        "grammar.preposition",
        Family.GRAMMAR,
        2,
        "grammar_rewrite",
        _COACH,
        True,
        "Wrong preposition, like 'discuss about'",
    ),
    _definition(
        "grammar.agreement",
        Family.GRAMMAR,
        2,
        "grammar_rewrite",
        _COACH,
        False,
        "Subject and verb do not agree, like 'she go'",
    ),
    _definition(
        "grammar.plural",
        Family.GRAMMAR,
        1,
        "grammar_rewrite",
        _COACH,
        False,
        "Missing or wrong plural ending",
    ),
    _definition(
        "structure.missing_point",
        Family.STRUCTURE,
        3,
        "pre_builder",
        _COACH,
        False,
        "Answer never states its main point",
    ),
    _definition(
        "structure.buried_point",
        Family.STRUCTURE,
        3,
        "pre_builder",
        _COACH,
        False,
        "Main point comes too late in the answer",
    ),
    _definition(
        "structure.missing_reason",
        Family.STRUCTURE,
        2,
        "pre_builder",
        _COACH,
        False,
        "Point is made without a reason",
    ),
    _definition(
        "structure.missing_example",
        Family.STRUCTURE,
        2,
        "pre_builder",
        _COACH,
        False,
        "Point is made without an example",
    ),
    _definition(
        "clarity.run_on",
        Family.CLARITY,
        2,
        "clarity_rewrite",
        _COACH,
        False,
        "Sentences strung together without a clear stop",
    ),
    _definition(
        "clarity.vague",
        Family.CLARITY,
        2,
        "clarity_rewrite",
        _COACH,
        False,
        "Vague wording where a specific one would do",
    ),
    _definition(
        "clarity.wordy",
        Family.CLARITY,
        2,
        "clarity_rewrite",
        _COACH,
        False,
        "More words than the idea needs",
    ),
    _definition(
        "clarity.repetition",
        Family.CLARITY,
        1,
        "clarity_rewrite",
        _COACH,
        False,
        "Saying the same thing more than once",
    ),
)


def _dynamic(key: str) -> KeyDefinition | None:
    """Build a default definition for a well-formed sub or low key, else None."""
    parts = key.split(".")
    if len(parts) == 4 and f"{parts[0]}.{parts[1]}" == Family.SUB:
        expected, produced = parts[2], parts[3]
        if _is_phone(expected) and _is_phone(produced) and expected != produced:
            return _definition(
                key,
                Family.SUB,
                1,
                "minimal_pairs",
                _SUB_DETECTORS,
                False,
                _sub_description(expected, produced),
            )
    elif len(parts) == 3 and f"{parts[0]}.{parts[1]}" == Family.LOW and _is_phone(parts[2]):
        return _definition(
            key,
            Family.LOW,
            1,
            "sound_practice",
            _LOW_DETECTORS,
            False,
            _low_description(parts[2]),
        )
    return None


class Taxonomy:
    def __init__(self, definitions: Iterable[KeyDefinition], version: int) -> None:
        self.version = version
        self._by_key = {d.key: d for d in definitions}

    def get(self, key: str) -> KeyDefinition:
        explicit = self._by_key.get(key)
        if explicit is not None:
            return explicit
        generated = _dynamic(key)
        if generated is None:
            raise UnknownErrorKey(key)
        return generated

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return key in self._by_key or _dynamic(key) is not None

    def defined(self) -> tuple[KeyDefinition, ...]:
        return tuple(sorted(self._by_key.values(), key=lambda d: d.key))


DEFAULT_TAXONOMY = Taxonomy(_EXPLICIT, TAXONOMY_VERSION)
