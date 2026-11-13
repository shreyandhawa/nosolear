"""Local Whisper transcripts: the stored payload to a `Transcript` (ARCHITECTURE.md section 15).

The libraries return objects, not JSON, so each local adapter writes one payload shape:
`{"engine", "model": {"repo_id", "revision"}, "fillers_kept", "text", "words": [...]}`, where each
word is `{"word", "start", "end", "probability"}` with times in seconds. Times become milliseconds
through `clean_word_timings`. Pure: no I/O.
"""

import math
from collections.abc import Mapping, Sequence
from typing import cast

from nosolear.domain.errors import MalformedProviderResponse
from nosolear.domain.results.words import clean_word_timings
from nosolear.domain.speech import RawResult, Transcript

_MALFORMED = "The local transcriber returned a transcript Nosolear can't read"


def _malformed() -> MalformedProviderResponse:
    return MalformedProviderResponse(_MALFORMED)


def _ms(seconds: object) -> float:
    """Milliseconds from seconds; a missing or non-numeric time is NaN, which cleaning drops."""
    if isinstance(seconds, bool) or not isinstance(seconds, int | float):
        return math.nan
    return float(seconds) * 1000


def parse_local_transcript(raw: RawResult) -> Transcript:
    payload = raw.payload
    text = payload.get("text")
    fillers_kept = payload.get("fillers_kept")
    words = payload.get("words")
    if (
        not isinstance(text, str)
        or not isinstance(fillers_kept, bool)
        or not isinstance(words, list)
    ):
        raise _malformed()
    timings: list[tuple[str, float, float, float | None]] = []
    for item in cast("Sequence[object]", words):
        if not isinstance(item, dict):
            raise _malformed()
        entry = cast("Mapping[str, object]", item)
        word = entry.get("word")
        if not isinstance(word, str):
            raise _malformed()
        probability = entry.get("probability")
        confidence = (
            float(probability)
            if isinstance(probability, int | float) and not isinstance(probability, bool)
            else None
        )
        timings.append((word, _ms(entry.get("start")), _ms(entry.get("end")), confidence))
    return Transcript(
        text=text.strip(),
        words=clean_word_timings(timings),
        fillers_kept=fillers_kept,
        raw=raw,
    )
