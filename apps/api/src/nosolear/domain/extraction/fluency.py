"""Fluency opportunities from the ASR transcript (`asr_metrics`, section 6.2). Pure.

Unscripted steps only. `fluency.slow_start` is judged once, on quick answers; the other keys are
judged once per sentence.
"""

import string
from collections.abc import Sequence
from typing import Final

from nosolear.domain.extraction.opportunities import Opportunity, ThresholdsFor
from nosolear.domain.speech import Transcript, WordTiming

UNSCRIPTED_STEPS: Final = frozenset({"speak", "quick_answer", "articulate"})
FILLERS: Final = frozenset({"um", "uh", "uhm", "er", "erm", "ah", "hmm", "mm"})
SLOW_START: Final = "fluency.slow_start"
FILLER: Final = "fluency.filler"
LONG_PAUSE: Final = "fluency.long_pause"
FALSE_START: Final = "fluency.false_start"
SENTENCE_KEYS: Final = (FALSE_START, FILLER, LONG_PAUSE)
_PUNCTUATION: Final = string.punctuation + "\u201c\u201d\u2018\u2019\u2014\u2013\u2026"
_MAX_REPEAT_WORDS: Final = 3
_SENTENCE_END: Final = (".", "?", "!")


def normalize(word: str) -> str:
    return word.lower().strip(_PUNCTUATION)


def sentences(words: Sequence[WordTiming]) -> list[tuple[WordTiming, ...]]:
    """Split at words whose text ends in a full stop, question mark or exclamation mark. Words
    left after the last such word form a final sentence."""
    out: list[tuple[WordTiming, ...]] = []
    current: list[WordTiming] = []
    for word in words:
        current.append(word)
        if word.text.endswith(_SENTENCE_END):
            out.append(tuple(current))
            current = []
    if current:
        out.append(tuple(current))
    return out


def _content_tokens(sentence: Sequence[WordTiming]) -> list[str]:
    tokens = (normalize(w.text) for w in sentence)
    return [t for t in tokens if t and t not in FILLERS]


def _repeats(tokens: Sequence[str]) -> bool:
    """True when some run of 1 to 3 words is immediately followed by the same run."""
    for size in range(1, _MAX_REPEAT_WORDS + 1):
        for start in range(len(tokens) - 2 * size + 1):
            if tokens[start : start + size] == tokens[start + size : start + 2 * size]:
                return True
    return False


def _long_pause(
    words: Sequence[WordTiming], first: int, end: int, limit: int, is_first: bool
) -> bool:
    """A gap longer than `limit` between consecutive words. The gap before the sentence's first
    word counts, except for the first sentence of the answer."""
    lo = first + 1 if is_first else first
    return any(words[j].start_ms - words[j - 1].end_ms > limit for j in range(max(lo, 1), end))


def _span(sentence: Sequence[WordTiming]) -> dict[str, object]:
    return {
        "start_ms": sentence[0].start_ms,
        "end_ms": sentence[-1].end_ms,
        "text": " ".join(w.text for w in sentence),
    }


def fluency_opportunities(
    transcript: Transcript, *, step: str, keys: frozenset[str], thresholds_for: ThresholdsFor
) -> list[Opportunity]:
    if step not in UNSCRIPTED_STEPS:
        return []
    words = transcript.words
    out: list[Opportunity] = []
    if step == "quick_answer" and SLOW_START in keys:
        first_ms = words[0].start_ms if words else None
        limit = thresholds_for(SLOW_START).slow_start_ms
        missed = first_ms is None or first_ms > limit
        out.append(Opportunity(SLOW_START, missed, {"first_word_ms": first_ms}))

    sentence_keys = [key for key in sorted(keys) if key in SENTENCE_KEYS]
    first = 0
    for index, sentence in enumerate(sentences(words)):
        end = first + len(sentence)
        span = _span(sentence)
        for key in sentence_keys:
            if key == FALSE_START:
                missed = _repeats(_content_tokens(sentence))
                out.append(Opportunity(key, missed, span))
            elif key == FILLER:
                missed = any(normalize(w.text) in FILLERS for w in sentence)
                out.append(
                    Opportunity(key, missed, {**span, "undercounted": not transcript.fillers_kept})
                )
            else:
                limit = thresholds_for(LONG_PAUSE).long_pause_ms
                missed = _long_pause(words, first, end, limit, is_first=index == 0)
                out.append(Opportunity(key, missed, span))
        first = end
    return out
