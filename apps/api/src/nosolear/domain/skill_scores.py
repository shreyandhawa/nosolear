"""Per-skill scores from one session's evidence: the components of section 6.9, combined pure.

A component is either available or absent. A skill with no available component is omitted, and
its score is the unweighted mean of the available component scores. The anchors are config values
to be tuned after Phase 1. Pure: no I/O.
"""

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from nosolear.domain.coach import Rubric
from nosolear.domain.extraction.fluency import FILLERS, normalize
from nosolear.domain.observations import Observation, Outcome
from nosolear.domain.speech import PronunciationAssessment, Transcript, WordTiming
from nosolear.domain.taxonomy import Skill

RUN_GAP_MS = 250
_MS_PER_MINUTE = 60_000
Component = tuple[float, float]
"""A component's raw value and its 0 to 100 score."""


@dataclass(frozen=True, slots=True)
class SessionEvidence:
    scripted_pronunciation: tuple[PronunciationAssessment, ...]
    sound_observations: tuple[Observation, ...]
    quick_answers: tuple[Transcript, ...]
    unscripted: tuple[Transcript, ...]
    grammar_misses: int
    articulate_rubric: Rubric | None


@dataclass(frozen=True, slots=True)
class SkillScore:
    skill: Skill
    score: float
    values: Mapping[str, float]
    scores: Mapping[str, float]


def linear_score(value: float, *, zero_at: float, full_at: float) -> float:
    """100 at `full_at`, 0 at `zero_at`, linear in between, clamped to [0, 100]."""
    fraction = (value - zero_at) / (full_at - zero_at)
    return min(100.0, max(0.0, 100.0 * fraction))


def _sounds(evidence: SessionEvidence) -> dict[str, Component]:
    out: dict[str, Component] = {}
    accuracies = [
        word.accuracy
        for assessment in evidence.scripted_pronunciation
        for word in assessment.words
        if word.accuracy is not None
    ]
    if accuracies:
        mean = statistics.fmean(accuracies)
        out["accuracy"] = (mean, mean)
    weights = [o.weight for o in evidence.sound_observations]
    total = sum(weights)
    if total > 0:
        missed = sum(o.weight for o in evidence.sound_observations if o.outcome is Outcome.MISS)
        hit_share = 1 - missed / total
        out["tracked_hit_share"] = (hit_share, 100 * hit_share)
    return out


def _speech_seconds(transcripts: Sequence[Transcript]) -> float:
    milliseconds = sum(t.words[-1].end_ms - t.words[0].start_ms for t in transcripts if t.words)
    return milliseconds / _MS_PER_MINUTE


def _is_filler(word: WordTiming) -> bool:
    return normalize(word.text) in FILLERS


def _run_lengths(transcript: Transcript) -> list[int]:
    """Runs of non-filler words, split at a filler or a gap of at least RUN_GAP_MS."""
    runs: list[int] = []
    current = 0
    previous: WordTiming | None = None
    for word in transcript.words:
        if _is_filler(word):
            if current:
                runs.append(current)
            current = 0
            previous = None
            continue
        if previous is not None and word.start_ms - previous.end_ms >= RUN_GAP_MS and current:
            runs.append(current)
            current = 0
        current += 1
        previous = word
    if current:
        runs.append(current)
    return runs


def _on_the_spot(evidence: SessionEvidence) -> dict[str, Component]:
    out: dict[str, Component] = {}
    firsts = [t.words[0].start_ms for t in evidence.quick_answers if t.words]
    if firsts:
        median = float(statistics.median(firsts))
        out["median_first_word_ms"] = (median, linear_score(median, zero_at=5000, full_at=1000))
    minutes = _speech_seconds(evidence.unscripted)
    words = [w for t in evidence.unscripted for w in t.words]
    if minutes > 0:
        fillers = sum(1 for w in words if _is_filler(w))
        fillers_per_min = fillers / minutes
        out["fillers_per_min"] = (
            fillers_per_min,
            linear_score(fillers_per_min, zero_at=12, full_at=0),
        )
        content_per_min = (len(words) - fillers) / minutes
        out["words_per_min"] = (
            content_per_min,
            linear_score(content_per_min, zero_at=60, full_at=150),
        )
    runs = [length for t in evidence.unscripted for length in _run_lengths(t)]
    if runs:
        mean_run = statistics.fmean(runs)
        out["mean_length_of_run"] = (mean_run, linear_score(mean_run, zero_at=2, full_at=12))
    if words:
        per_100 = evidence.grammar_misses * 100 / len(words)
        out["grammar_errors_per_100_words"] = (
            per_100,
            linear_score(per_100, zero_at=10, full_at=0),
        )
    return out


def _articulate(evidence: SessionEvidence) -> dict[str, Component]:
    rubric = evidence.articulate_rubric
    if rubric is None:
        return {}
    mean = statistics.fmean([rubric.structure, rubric.clarity, rubric.concision])
    return {"rubric": (mean, 25 * mean)}


_COMPONENTS = (
    (Skill.SOUNDS, _sounds),
    (Skill.ON_THE_SPOT, _on_the_spot),
    (Skill.ARTICULATE, _articulate),
)


def skill_scores(evidence: SessionEvidence) -> tuple[SkillScore, ...]:
    out: list[SkillScore] = []
    for skill, components in _COMPONENTS:
        found = components(evidence)
        if not found:
            continue
        scores = {name: score for name, (_, score) in found.items()}
        out.append(
            SkillScore(
                skill=skill,
                score=statistics.fmean(scores.values()),
                values={name: value for name, (value, _) in found.items()},
                scores=scores,
            )
        )
    return tuple(out)


__all__ = [
    "RUN_GAP_MS",
    "SessionEvidence",
    "SkillScore",
    "linear_score",
    "skill_scores",
]
