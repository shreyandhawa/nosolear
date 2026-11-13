"""Word timings cleaned for storage: the one place that decides what a usable word timing is.

Input is `(text, start_ms, end_ms, confidence)` as floats, straight from a provider. Words with no
text, or with a non-finite time, are dropped. Times are clamped to `0 <= start <= end` and rounded
to whole milliseconds, and the result is sorted by start (a stable sort, so equal starts keep their
order). Pure: no I/O.
"""

import math
from collections.abc import Iterable

from nosolear.domain.speech import WordTiming


def clean_word_timings(
    words: Iterable[tuple[str, float, float, float | None]],
) -> tuple[WordTiming, ...]:
    cleaned: list[WordTiming] = []
    for text, start, end, confidence in words:
        stripped = text.strip()
        if not stripped or not (math.isfinite(start) and math.isfinite(end)):
            continue
        start_ms = round(max(0.0, start))
        end_ms = max(start_ms, round(max(0.0, end)))
        score = confidence if confidence is not None and math.isfinite(confidence) else None
        cleaned.append(WordTiming(stripped, start_ms, end_ms, score))
    return tuple(sorted(cleaned, key=lambda word: word.start_ms))
