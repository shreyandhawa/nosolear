"""Sound and prosody opportunities from Azure pronunciation and phone-probe results (section 6.2).

Pure: no I/O. Only keys in `keys` produce opportunities. Output follows the words, then the
phones, then the keys sorted.
"""

from collections.abc import Iterable, Mapping
from typing import Final

from nosolear.domain.extraction.opportunities import Opportunity, ThresholdsFor
from nosolear.domain.extraction.phones import (
    ProbeWord,
    ends_with_consonant_cluster,
    is_vowel,
    probe_words,
    starts_with_s_cluster,
)
from nosolear.domain.speech import PhonemeAssessment, PhoneProbeResult, PronunciationAssessment
from nosolear.domain.speech import WordAssessment as Word

SKIPPED_ERRORS: Final = frozenset({"Omission", "Insertion"})
SUB_HEAD: Final = "sound.sub"
LOW_HEAD: Final = "sound.low"
EPENTHESIS_KEY: Final = "sound.ins.epenthesis_sC"
FINAL_CLUSTER_KEY: Final = "sound.del.final_cluster"
PROSODY_FLAGS: Final = {
    "prosody.unexpected_break": "UnexpectedBreak",
    "prosody.missing_break": "MissingBreak",
}
MONOTONE_KEY: Final = "prosody.monotone"
MONOTONE_FLAG: Final = "Monotone"


def clear_substitute(phoneme: PhonemeAssessment, margin: float) -> str | None:
    """The n-best candidate that clearly beats the expected phone, or None.

    The expected phone scores 0 when it is absent from the n-best list.
    """
    if not phoneme.nbest:
        return None
    top = min(phoneme.nbest, key=lambda c: (-c.score, c.phoneme))
    if top.phoneme == phoneme.phoneme:
        return None
    expected_score = max(
        (c.score for c in phoneme.nbest if c.phoneme == phoneme.phoneme), default=0.0
    )
    if top.score - expected_score >= margin:
        return top.phoneme
    return None


def _sub_index(keys: Iterable[str]) -> dict[str, list[tuple[str, str]]]:
    """Expected phone to (key, produced phone) pairs, keys sorted."""
    index: dict[str, list[tuple[str, str]]] = {}
    for key in sorted(keys):
        parts = key.rsplit(".", 2)
        if len(parts) == 3 and parts[0] == SUB_HEAD:
            index.setdefault(parts[1], []).append((key, parts[2]))
    return index


def _low_index(keys: Iterable[str]) -> dict[str, str]:
    """Phone to its `sound.low.<phone>` key."""
    index: dict[str, str] = {}
    for key in keys:
        head, _, phone = key.rpartition(".")
        if head == LOW_HEAD and phone:
            index[phone] = key
    return index


def _word_evidence(word: Word) -> dict[str, object]:
    return {
        "word": word.word,
        "start_ms": word.start_ms,
        "end_ms": word.end_ms,
        "expected": None,
        "produced": None,
        "score": None,
    }


def _phone_opportunities(
    word: Word,
    phoneme: PhonemeAssessment,
    *,
    subs: Mapping[str, list[tuple[str, str]]],
    lows: Mapping[str, str],
    has_nbest: bool,
    thresholds_for: ThresholdsFor,
) -> list[tuple[str, Opportunity]]:
    found: list[tuple[str, Opportunity]] = []
    for key, produced in subs.get(phoneme.phoneme, []) if has_nbest else []:
        evidence = {
            **_word_evidence(word),
            "expected": phoneme.phoneme,
            "produced": produced,
            "score": phoneme.accuracy,
        }
        missed = clear_substitute(phoneme, thresholds_for(key).nbest_margin) == produced
        found.append((key, Opportunity(key, missed, evidence)))
    low_key = lows.get(phoneme.phoneme)
    if low_key is not None:
        limits = thresholds_for(low_key)
        substitute = clear_substitute(phoneme, limits.nbest_margin) if has_nbest else None
        missed = substitute is None and phoneme.accuracy < limits.low_accuracy
        evidence = {
            **_word_evidence(word),
            "expected": phoneme.phoneme,
            "produced": None,
            "score": phoneme.accuracy,
        }
        found.append((low_key, Opportunity(low_key, missed, evidence)))
    return sorted(found, key=lambda pair: pair[0])


def azure_opportunities(
    result: PronunciationAssessment, *, keys: frozenset[str], thresholds_for: ThresholdsFor
) -> list[Opportunity]:
    subs = _sub_index(keys)
    lows = _low_index(keys)
    scored = [word for word in result.words if word.error_type not in SKIPPED_ERRORS]
    out: list[Opportunity] = []
    for position, word in enumerate(scored):
        for phoneme in word.phonemes:
            out.extend(
                opp
                for _, opp in _phone_opportunities(
                    word,
                    phoneme,
                    subs=subs,
                    lows=lows,
                    has_nbest=result.has_nbest,
                    thresholds_for=thresholds_for,
                )
            )
        if result.has_prosody:
            out.extend(_word_prosody(word, position, keys))
    if result.has_prosody and scored and MONOTONE_KEY in keys:
        missed = any(
            word.prosody is not None and MONOTONE_FLAG in word.prosody.error_types
            for word in scored
        )
        out.append(Opportunity(MONOTONE_KEY, missed, _clip_evidence()))
    return out


def _word_prosody(word: Word, position: int, keys: frozenset[str]) -> list[Opportunity]:
    """Break flags on every scored word after the first; the first word has no break to judge."""
    if position == 0:
        return []
    flags = word.prosody.error_types if word.prosody is not None else ()
    return [
        Opportunity(key, flag in flags, _word_evidence(word))
        for key, flag in sorted(PROSODY_FLAGS.items())
        if key in keys
    ]


def _clip_evidence() -> dict[str, object]:
    return {
        "word": None,
        "start_ms": None,
        "end_ms": None,
        "expected": None,
        "produced": None,
        "score": None,
    }


def _probe_evidence(word: ProbeWord, *, expected: str, produced: str | None) -> dict[str, object]:
    return {
        "word": word.text,
        "start_ms": None,
        "end_ms": None,
        "expected": expected,
        "produced": produced,
        "score": None,
    }


def probe_opportunities(
    result: PhoneProbeResult, *, reference_text: str | None, keys: frozenset[str]
) -> list[Opportunity]:
    subs = _sub_index(keys)
    out: list[Opportunity] = []
    for word in probe_words(result, reference_text=reference_text):
        for edit in word.edits:
            if edit.expected is None or edit.op == "ins":
                continue
            for key, produced in subs.get(edit.expected, []):
                missed = edit.op == "sub" and edit.heard == produced
                evidence = _probe_evidence(
                    word,
                    expected=edit.expected,
                    produced=edit.heard if edit.op == "sub" else None,
                )
                out.append(Opportunity(key, missed, evidence))
        out.extend(_probe_cluster_opportunities(word, keys))
    return out


def _probe_cluster_opportunities(word: ProbeWord, keys: frozenset[str]) -> list[Opportunity]:
    out: list[Opportunity] = []
    phrase = " ".join(word.expected)
    if EPENTHESIS_KEY in keys and starts_with_s_cluster(word.expected):
        inserted = [
            edit.heard
            for edit in word.edits
            if edit.op == "ins" and edit.expected_index == 0 and edit.heard is not None
        ]
        vowel = next((heard for heard in inserted if is_vowel(heard)), None)
        out.append(
            Opportunity(
                EPENTHESIS_KEY,
                vowel is not None,
                _probe_evidence(word, expected=phrase, produced=vowel),
            )
        )
    if FINAL_CLUSTER_KEY in keys and ends_with_consonant_cluster(word.expected):
        last = len(word.expected) - 1
        missed = any(edit.op == "del" and edit.expected_index == last for edit in word.edits)
        out.append(
            Opportunity(
                FINAL_CLUSTER_KEY, missed, _probe_evidence(word, expected=phrase, produced=None)
            )
        )
    return out
