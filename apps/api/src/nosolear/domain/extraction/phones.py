"""Phone-probe helpers: s-clusters, final clusters and the probe split into words. Pure."""

from collections.abc import Sequence
from dataclasses import dataclass, replace

from nosolear.domain.phone_alignment import PhoneEdit, align_phones
from nosolear.domain.phones import AZURE_CONSONANTS, AZURE_VOWELS
from nosolear.domain.speech import PhoneProbeResult


def is_vowel(phone: str) -> bool:
    return phone in AZURE_VOWELS


def starts_with_s_cluster(phones: Sequence[str]) -> bool:
    return len(phones) >= 2 and phones[0] == "s" and phones[1] in AZURE_CONSONANTS


def ends_with_consonant_cluster(phones: Sequence[str]) -> bool:
    return len(phones) >= 2 and phones[-2] in AZURE_CONSONANTS and phones[-1] in AZURE_CONSONANTS


@dataclass(frozen=True, slots=True)
class ProbeWord:
    text: str | None
    expected: tuple[str, ...]
    edits: tuple[PhoneEdit, ...]
    """Each edit's `expected_index` is relative to this word."""


def _owner(index: int, spans: Sequence[tuple[int, int]]) -> int | None:
    """The word whose span holds `index`. An index past the last phone belongs to the last word."""
    for word, (start, end) in enumerate(spans):
        if start <= index < end:
            return word
    return len(spans) - 1 if spans else None


def probe_words(result: PhoneProbeResult, *, reference_text: str | None) -> tuple[ProbeWord, ...]:
    edits = align_phones(result.expected, result.heard)
    tokens = reference_text.split() if reference_text is not None else None
    use_text = tokens is not None and len(tokens) == len(result.expected_words)

    spans: list[tuple[int, int]] = []
    start = 0
    for word in result.expected_words:
        spans.append((start, start + len(word)))
        start += len(word)

    per_word: list[list[PhoneEdit]] = [[] for _ in result.expected_words]
    for edit in edits:
        owner = _owner(edit.expected_index, spans)
        if owner is None:
            continue
        offset = spans[owner][0]
        per_word[owner].append(replace(edit, expected_index=edit.expected_index - offset))

    return tuple(
        ProbeWord(
            text=tokens[i] if use_text and tokens is not None else None,
            expected=tuple(word),
            edits=tuple(per_word[i]),
        )
        for i, word in enumerate(result.expected_words)
    )
