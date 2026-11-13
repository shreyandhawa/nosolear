"""Azure speech-to-text: the stored payload to a `Transcript` (ARCHITECTURE.md section 5).

The payload is `{"results": [...]}`, one detailed-format JSON per recognized phrase. The text is
the phrases' `DisplayText` joined with a space. Word times come from each phrase's first n-best
entry, in 100 ns ticks, converted to milliseconds. Pure: no I/O.
"""

from collections.abc import Mapping, Sequence
from typing import cast

from nosolear.domain.errors import MalformedProviderResponse
from nosolear.domain.results.words import clean_word_timings
from nosolear.domain.speech import RawResult, Transcript, WordTiming

TICKS_PER_MS = 10_000
_MALFORMED = "Azure returned a transcript Nosolear can't read"


def _malformed() -> MalformedProviderResponse:
    return MalformedProviderResponse(_MALFORMED)


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise _malformed()
    return cast("Mapping[str, object]", value)


def _ms(ticks: object) -> float:
    """Milliseconds from ticks; a missing or non-numeric time is NaN, which cleaning drops."""
    if isinstance(ticks, bool) or not isinstance(ticks, int | float):
        return float("nan")
    return ticks / TICKS_PER_MS


def _phrase_words(phrase: Mapping[str, object]) -> Sequence[object]:
    nbest = phrase.get("NBest")
    if not isinstance(nbest, list) or not nbest:
        return ()
    first = _mapping(cast("list[object]", nbest)[0])
    words = first.get("Words")
    if words is None:
        return ()
    if not isinstance(words, list):
        raise _malformed()
    return cast("Sequence[object]", words)


def parse_azure_stt(raw: RawResult) -> Transcript:
    results = raw.payload.get("results")
    if results is None:
        results = []
    if not isinstance(results, list):
        raise _malformed()
    texts: list[str] = []
    timings: list[tuple[str, float, float, float | None]] = []
    for item in cast("Sequence[object]", results):
        phrase = _mapping(item)
        display = phrase.get("DisplayText")
        if isinstance(display, str) and display.strip():
            texts.append(display.strip())
        for word_item in _phrase_words(phrase):
            word = _mapping(word_item)
            start = _ms(word.get("Offset"))
            confidence = word.get("Confidence")
            score = float(confidence) if isinstance(confidence, int | float) else None
            end = start + _ms(word.get("Duration"))
            timings.append((str(word.get("Word", "")), start, end, score))
    words: tuple[WordTiming, ...] = clean_word_timings(timings)
    return Transcript(
        text=" ".join(texts),
        words=words,
        fillers_kept=False,
        raw=raw,
    )
