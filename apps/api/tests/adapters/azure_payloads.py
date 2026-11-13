"""Hand-written Azure result payloads (detailed JSON) for the adapter and parser tests.

Offsets and durations are given in milliseconds and written as 100 ns ticks, the unit Azure
reports. Nothing here is recorded from the live service; the live tests check the real shapes.
"""

from collections.abc import Iterable, Mapping, Sequence

TICKS_PER_MS = 10_000


def _ticks(ms: float | None) -> int | None:
    return None if ms is None else int(ms * TICKS_PER_MS)


def pa_phoneme(
    phoneme: str,
    accuracy: float | None,
    *,
    nbest: Iterable[tuple[str, float]] = (),
    offset_ms: float | None,
    duration_ms: float | None,
) -> dict[str, object]:
    return {
        "Phoneme": phoneme,
        "PronunciationAssessment": {
            "AccuracyScore": accuracy,
            "NBestPhonemes": [{"Phoneme": p, "Score": s} for p, s in nbest],
        },
        "Offset": _ticks(offset_ms),
        "Duration": _ticks(duration_ms),
    }


def pa_word(
    word: str,
    accuracy: float | None,
    *,
    error_type: str = "None",
    offset_ms: float | None,
    duration_ms: float | None,
    phonemes: Sequence[dict[str, object]] = (),
    prosody: Mapping[str, object] | None = None,
) -> dict[str, object]:
    assessment: dict[str, object] = {"AccuracyScore": accuracy, "ErrorType": error_type}
    if prosody is not None:
        assessment["Feedback"] = {"Prosody": prosody}
    return {
        "Word": word,
        "Offset": _ticks(offset_ms),
        "Duration": _ticks(duration_ms),
        "PronunciationAssessment": assessment,
        "Phonemes": list(phonemes),
    }


def pa_phrase(
    words: Sequence[dict[str, object]],
    *,
    accuracy: object = 90.0,
    fluency: object = 90.0,
    completeness: object = 100.0,
    prosody: object = None,
) -> dict[str, object]:
    """One recognized phrase in the detailed format, scored through its first n-best entry."""
    assessment: dict[str, object] = {
        "AccuracyScore": accuracy,
        "FluencyScore": fluency,
        "CompletenessScore": completeness,
    }
    if prosody is not None:
        assessment["ProsodyScore"] = prosody
    return {
        "RecognitionStatus": "Success",
        "NBest": [{"Confidence": 0.9, "PronunciationAssessment": assessment, "Words": list(words)}],
    }


def no_match() -> dict[str, object]:
    return {"RecognitionStatus": "NoMatch"}


def stt_phrase(display: str, words: Sequence[tuple[str, float, float, float]]) -> dict[str, object]:
    """One phrase in the detailed transcription format: `words` are (text, offset_ms, dur_ms,
    confidence)."""
    return {
        "RecognitionStatus": "Success",
        "DisplayText": display,
        "NBest": [
            {
                "Confidence": 0.9,
                "Words": [
                    {
                        "Word": text,
                        "Offset": _ticks(offset_ms),
                        "Duration": _ticks(duration_ms),
                        "Confidence": confidence,
                    }
                    for text, offset_ms, duration_ms, confidence in words
                ],
            }
        ],
    }
