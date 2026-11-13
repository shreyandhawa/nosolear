"""Feedback logic: which fix each skill gets, and how the coach's words are kept or replaced.

Pure. The domain picks the fix (the LLM never does, §6.7). Coach text is untrusted: it is
checked here, and anything that does not pass becomes a template, never a silent gap.
"""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from nosolear.domain.coach import MAX_EXPLANATION_CHARS, MAX_MODEL_TEXT_CHARS, CoachExplanation
from nosolear.domain.observations import Outcome
from nosolear.domain.profile import Profile
from nosolear.domain.selection import SKILL_ORDER
from nosolear.domain.taxonomy import Family, Skill, Taxonomy
from nosolear.ports.feedback import StoredObservation

# Families whose coach rewrite is shown as model_text. Sounds use the word from the audio and
# fluency has no model text at all.
_REWRITE_FAMILIES = frozenset({Family.GRAMMAR, Family.STRUCTURE, Family.CLARITY})
_WORD_FAMILIES = frozenset({Family.SUB, Family.LOW, Family.INS, Family.DEL, Family.PROSODY})
_EVIDENCE_CAP = 100


class SkillState(StrEnum):
    FIX = "fix"
    CLEAN = "clean"
    NOT_SCORED = "not_scored"


class SessionNotFound(ValueError):
    """No session has this id."""


class SessionNotDaily(ValueError):
    """Feedback is only made for a daily session."""


class SessionNotAnalyzed(ValueError):
    """The analysis job is still queued or running, so the observations are not final."""


@dataclass(frozen=True, slots=True)
class FixChoice:
    skill: Skill
    error_key: str
    observation_id: int
    attempt_id: str | None
    word: str | None
    quote: str | None
    context: str | None
    start_ms: int | None
    end_ms: int | None
    priority: float


@dataclass(frozen=True, slots=True)
class SkillOutcome:
    skill: Skill
    state: SkillState
    fix: FixChoice | None


@dataclass(frozen=True, slots=True)
class Explanation:
    error_key: str
    message: str
    model_text: str | None


def _text_of(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _int_of(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _fix_from(key: str, skill: Skill, stored: StoredObservation, priority: float) -> FixChoice:
    evidence = stored.observation.evidence
    return FixChoice(
        skill=skill,
        error_key=key,
        observation_id=stored.id,
        attempt_id=stored.observation.attempt_id,
        word=_text_of(evidence.get("word")),
        quote=_text_of(evidence.get("quote")),
        context=_text_of(evidence.get("text")),
        start_ms=_int_of(evidence.get("start_ms")),
        end_ms=_int_of(evidence.get("end_ms")),
        priority=priority,
    )


def choose_fixes(
    *,
    session_observations: Sequence[StoredObservation],
    profile: Profile,
    taxonomy: Taxonomy,
) -> tuple[SkillOutcome, ...]:
    """One outcome per skill in SKILL_ORDER: a fix, clean, or not scored (never invented)."""
    priority_of = {entry.definition.key: entry.priority for entry in profile.entries}
    outcomes: list[SkillOutcome] = []
    for skill in SKILL_ORDER:
        mine = [
            s for s in session_observations if taxonomy.get(s.observation.error_key).skill is skill
        ]
        if not mine:
            outcomes.append(SkillOutcome(skill, SkillState.NOT_SCORED, None))
            continue
        misses = [s for s in mine if s.observation.outcome is Outcome.MISS]
        if not misses:
            outcomes.append(SkillOutcome(skill, SkillState.CLEAN, None))
            continue
        by_key: dict[str, list[StoredObservation]] = {}
        for miss in misses:
            by_key.setdefault(miss.observation.error_key, []).append(miss)

        def priority(key: str) -> float:
            if key in priority_of:
                return priority_of[key]
            return 1.0 * taxonomy.get(key).impact

        key = min(by_key, key=lambda k: (-priority(k), k))
        evidence = min(
            by_key[key],
            key=lambda s: (-s.observation.weight, s.observation.observed_at, s.id),
        )
        outcomes.append(
            SkillOutcome(skill, SkillState.FIX, _fix_from(key, skill, evidence, priority(key)))
        )
    return tuple(outcomes)


def _clean(raw: str) -> str:
    """Whitespace becomes a space; control and format characters (bidi overrides too) go."""
    spaced = "".join(" " if ch.isspace() else ch for ch in raw)
    kept = "".join(ch for ch in spaced if unicodedata.category(ch) not in ("Cc", "Cf"))
    return " ".join(kept.split())


def _model_text(fix: FixChoice, taxonomy: Taxonomy, rewrite: str | None) -> str | None:
    family = taxonomy.get(fix.error_key).family
    if family in _REWRITE_FAMILIES:
        return None if rewrite is None else rewrite[:MAX_MODEL_TEXT_CHARS] or None
    if family in _WORD_FAMILIES:
        return fix.word
    return None


def sanitize_explanation(
    raw: CoachExplanation | None, *, fix: FixChoice, taxonomy: Taxonomy
) -> Explanation | None:
    """Turn the coach's untrusted reply into plain text, or None when it cannot be used."""
    if raw is None:
        return None
    message = _clean(raw.message)
    if not 0 < len(message) <= MAX_EXPLANATION_CHARS:
        return None
    rewrite = _clean(raw.model_text) or None
    return Explanation(
        error_key=fix.error_key,
        message=message,
        model_text=_model_text(fix, taxonomy, rewrite),
    )


def _evidence_phrase(fix: FixChoice) -> str:
    if fix.word:
        return f' It came up on "{fix.word[:_EVIDENCE_CAP]}".'
    if fix.quote:
        return f' It came up in "{fix.quote[:_EVIDENCE_CAP]}".'
    return ""


_NEXT_STEP: dict[Family, str] = {
    Family.SUB: "Practise the sound in a few short words, then in a sentence.",
    Family.LOW: "Practise the sound in a few short words, then in a sentence.",
    Family.INS: "Say the word slowly and check for the extra sound.",
    Family.DEL: "Say the word slowly and check that the last sound is there.",
    Family.PROSODY: "Say the sentence once more with the stress or pause on purpose.",
    Family.FLUENCY: "Pause for a breath, then finish the thought.",
    Family.GRAMMAR: "Say the sentence again with the fix.",
    Family.STRUCTURE: "Say the point first, then the reason or example.",
    Family.CLARITY: "Say the sentence again, shorter and more exact.",
}


def template_explanation(fix: FixChoice, taxonomy: Taxonomy) -> Explanation:
    """A written explanation for when the coach cannot be used. It names the key and evidence."""
    definition = taxonomy.get(fix.error_key)
    message = (
        f"This session's clearest miss was: {definition.description}."
        f"{_evidence_phrase(fix)} {_NEXT_STEP[definition.family]}"
    )
    return Explanation(
        error_key=fix.error_key,
        message=message,
        model_text=_model_text(fix, taxonomy, None),
    )
