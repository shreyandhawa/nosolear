"""Azure pronunciation assessment: the stored payload to a `PronunciationAssessment` (section 5.1).

The payload is `{"mode", "reference_text", "results"}`, where `results` holds one detailed-format
JSON per recognized phrase, as the service returned it. Scores are read from each phrase's first
n-best entry. Offsets and durations arrive in 100 ns ticks and are converted to whole milliseconds.
"""

from collections.abc import Mapping, Sequence
from typing import cast

from nosolear.domain.errors import MalformedProviderResponse
from nosolear.domain.speech import (
    NBestPhoneme,
    PhonemeAssessment,
    PronunciationAssessment,
    ProsodyFeedback,
    RawResult,
    ScoringMode,
    WordAssessment,
)

TICKS_PER_MS = 10_000
_MALFORMED = "Azure returned a pronunciation result Nosolear can't read"


def _malformed() -> MalformedProviderResponse:
    return MalformedProviderResponse(_MALFORMED)


_EMPTY: Mapping[str, object] = {}


def _mapping(value: object) -> Mapping[str, object]:
    if value is None:
        return _EMPTY
    if not isinstance(value, dict):
        raise _malformed()
    return cast("Mapping[str, object]", value)


def _items(value: object) -> Sequence[object]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _malformed()
    return cast("Sequence[object]", value)


def _score(container: Mapping[str, object], key: str) -> float | None:
    value = container.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _malformed()
    return float(value)


def _required_score(container: Mapping[str, object], key: str) -> float:
    value = _score(container, key)
    if value is None:
        raise _malformed()
    return value


def _ms(ticks: object) -> int | None:
    if ticks is None:
        return None
    if isinstance(ticks, bool) or not isinstance(ticks, int) or ticks < 0:
        raise _malformed()
    return ticks // TICKS_PER_MS


def _span(offset: object, duration: object) -> tuple[int | None, int | None]:
    start = _ms(offset)
    length = _ms(duration)
    if start is None or length is None:
        return start, None
    return start, start + length


def _phoneme(raw: object) -> PhonemeAssessment:
    entry = _mapping(raw)
    assessment = _mapping(entry.get("PronunciationAssessment"))
    nbest = tuple(
        NBestPhoneme(
            phoneme=str(_mapping(item).get("Phoneme", "")),
            score=_required_score(_mapping(item), "Score"),
        )
        for item in _items(assessment.get("NBestPhonemes"))
    )
    start, end = _span(entry.get("Offset"), entry.get("Duration"))
    return PhonemeAssessment(
        phoneme=str(entry.get("Phoneme", "")),
        accuracy=_required_score(assessment, "AccuracyScore"),
        nbest=nbest,
        start_ms=start,
        end_ms=end,
    )


def _prosody(raw: object) -> ProsodyFeedback | None:
    if raw is None:
        return None
    prosody = _mapping(raw)
    breaks = _mapping(prosody.get("Break"))
    intonation = _mapping(prosody.get("Intonation"))
    unexpected = _mapping(breaks.get("UnexpectedBreak"))
    missing = _mapping(breaks.get("MissingBreak"))
    monotone = _mapping(_mapping(intonation.get("Monotone")))
    error_types = [
        *(str(t) for t in _items(breaks.get("ErrorTypes"))),
        *(str(t) for t in _items(intonation.get("ErrorTypes"))),
    ]
    return ProsodyFeedback(
        error_types=tuple(t for t in error_types if t != "None"),
        unexpected_break=_score(unexpected, "Confidence"),
        missing_break=_score(missing, "Confidence"),
        monotone=_score(monotone, "SyllablePitchDeltaConfidence"),
    )


def _word(raw: object) -> WordAssessment:
    entry = _mapping(raw)
    assessment = _mapping(entry.get("PronunciationAssessment"))
    start, end = _span(entry.get("Offset"), entry.get("Duration"))
    error_type = assessment.get("ErrorType", "None")
    feedback = _mapping(assessment.get("Feedback"))
    return WordAssessment(
        word=str(entry.get("Word", "")),
        accuracy=_score(assessment, "AccuracyScore"),
        error_type=str(error_type),
        start_ms=start,
        end_ms=end,
        phonemes=tuple(_phoneme(p) for p in _items(entry.get("Phonemes"))),
        prosody=_prosody(feedback.get("Prosody")),
    )


def _phrase_words(phrase: Mapping[str, object]) -> tuple[Mapping[str, object], list[object]]:
    """The phrase's first n-best entry and its words; a phrase that is not a success may have
    no n-best at all, which is an empty phrase rather than an error."""
    status = phrase.get("RecognitionStatus")
    nbest = _items(phrase.get("NBest"))
    if not nbest:
        if status == "Success":
            raise _malformed()
        return _EMPTY, []
    first = _mapping(nbest[0])
    return first, list(_items(first.get("Words")))


def _weighted(pairs: list[tuple[float, int]]) -> float | None:
    if not pairs:
        return None
    total = sum(weight for _, weight in pairs)
    if total == 0:
        return sum(score for score, _ in pairs) / len(pairs)
    return sum(score * weight for score, weight in pairs) / total


def parse_azure_pa(raw: RawResult) -> PronunciationAssessment:
    payload = raw.payload
    mode_name = payload.get("mode")
    if not isinstance(mode_name, str):
        raise _malformed()
    try:
        mode = ScoringMode(mode_name)
    except ValueError:
        raise _malformed() from None
    phrases = [_mapping(p) for p in _items(payload.get("results"))]

    words: list[WordAssessment] = []
    accuracy: list[tuple[float, int]] = []
    fluency: list[tuple[float, int]] = []
    completeness: list[tuple[float, int]] = []
    prosody_scores: list[tuple[float, int]] = []
    for phrase in phrases:
        first, raw_words = _phrase_words(phrase)
        phrase_words = [_word(w) for w in raw_words]
        words.extend(phrase_words)
        scores = _mapping(first.get("PronunciationAssessment"))
        weight = len(phrase_words)
        for key, bucket in (
            ("AccuracyScore", accuracy),
            ("FluencyScore", fluency),
            ("CompletenessScore", completeness),
            ("ProsodyScore", prosody_scores),
        ):
            value = _score(scores, key)
            if value is not None:
                bucket.append((value, weight))

    has_nbest = any(p.nbest for w in words for p in w.phonemes)
    has_prosody = bool(prosody_scores) or any(w.prosody is not None for w in words)
    return PronunciationAssessment(
        mode=mode,
        words=tuple(words),
        accuracy=_weighted(accuracy),
        fluency=_weighted(fluency),
        completeness=_weighted(completeness),
        prosody=_weighted(prosody_scores),
        has_nbest=has_nbest,
        has_prosody=has_prosody,
        raw=raw,
    )
