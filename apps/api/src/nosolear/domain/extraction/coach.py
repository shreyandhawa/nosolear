"""Coach opportunities (section 6.2). The coach output is untrusted, so every finding is re-checked
against the transcript and the step before it counts. Pure.

Tokens use the same rule as `domain/coach.py` (`[\\w']+` after casefolding), so a quote that
`quote_in_transcript` accepts is found in the same token stream here.
"""

import re
from collections.abc import Sequence
from typing import Final

from nosolear.domain.coach import (
    TASK_FAMILIES,
    CoachAnalysis,
    CoachFinding,
    coach_task_for_step,
    quote_in_transcript,
)
from nosolear.domain.extraction.fluency import sentences
from nosolear.domain.extraction.opportunities import Opportunity
from nosolear.domain.speech import Transcript, WordTiming
from nosolear.domain.taxonomy import Detector, Family, Taxonomy

_TOKEN: Final = re.compile(r"[\w']+")
_ANSWER_FAMILIES: Final = frozenset({Family.STRUCTURE, Family.CLARITY})


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.casefold())


def _allowed_families(step: str) -> frozenset[Family]:
    task = coach_task_for_step(step)
    return TASK_FAMILIES[task] if task is not None else frozenset()


def valid_findings(
    coach: CoachAnalysis, transcript: Transcript, *, step: str, taxonomy: Taxonomy
) -> list[CoachFinding]:
    families = _allowed_families(step)
    kept: list[CoachFinding] = []
    for finding in coach.findings:
        if finding.error_key not in taxonomy:
            continue
        definition = taxonomy.get(finding.error_key)
        if Detector.COACH not in definition.detectors or definition.family not in families:
            continue
        if finding.quote is None and definition.family is Family.GRAMMAR:
            continue
        if finding.quote is not None and not quote_in_transcript(finding.quote, transcript.text):
            continue
        kept.append(finding)
    return kept


def _keys_in(keys: frozenset[str], taxonomy: Taxonomy, wanted: frozenset[Family]) -> list[str]:
    return [
        key
        for key in sorted(keys)
        if key in taxonomy
        and taxonomy.get(key).family in wanted
        and Detector.COACH in taxonomy.get(key).detectors
    ]


def _first_at(wanted: Sequence[str], heard: Sequence[str]) -> int | None:
    size = len(wanted)
    for start in range(len(heard) - size + 1):
        if heard[start : start + size] == list(wanted):
            return start
    return None


def _answer_span(words: Sequence[WordTiming]) -> dict[str, object]:
    if not words:
        return {"start_ms": None, "end_ms": None}
    return {"start_ms": words[0].start_ms, "end_ms": words[-1].end_ms}


def coach_opportunities(
    coach: CoachAnalysis,
    transcript: Transcript,
    *,
    step: str,
    keys: frozenset[str],
    taxonomy: Taxonomy,
) -> list[Opportunity]:
    families = _allowed_families(step)
    findings = valid_findings(coach, transcript, step=step, taxonomy=taxonomy)
    parts = sentences(transcript.words)

    flat: list[str] = []
    ranges: list[tuple[int, int]] = []
    for sentence in parts:
        lo = len(flat)
        for word in sentence:
            flat.extend(_tokens(word.text))
        ranges.append((lo, len(flat)))

    located: list[tuple[str, int, str]] = []
    for finding in findings:
        if finding.quote is None:
            continue
        start = _first_at(_tokens(finding.quote), flat)
        if start is not None:
            located.append((finding.error_key, start, finding.quote))

    out: list[Opportunity] = []
    grammar = _keys_in(keys, taxonomy, families & {Family.GRAMMAR})
    for sentence, (lo, hi) in zip(parts, ranges, strict=True):
        span = _answer_span(sentence)
        for key in grammar:
            quotes = [quote for k, start, quote in located if k == key and lo <= start < hi]
            out.append(
                Opportunity(key, bool(quotes), {"quote": quotes[0] if quotes else None, **span})
            )

    answer = _answer_span(transcript.words)
    for key in _keys_in(keys, taxonomy, families & _ANSWER_FAMILIES):
        matched = [f for f in findings if f.error_key == key]
        out.append(
            Opportunity(
                key, bool(matched), {"quote": matched[0].quote if matched else None, **answer}
            )
        )
    return out
