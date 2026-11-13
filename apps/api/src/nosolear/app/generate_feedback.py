"""generate_feedback: one feedback card per skill for a finished daily session.

The coach is the only paid call here, so it is reached only after the typed session checks pass
and only for fixes that have no coach-written item yet. A failed call stores a template with its
reason instead of nothing. A later request therefore upgrades template items, and it never asks
the coach again for an item the coach already wrote. A skill's stored fix keeps its key, so the
upgrade explains what was shown and a newer profile cannot change it.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from nosolear.domain.errors import (
    CapabilityMissing,
    CapExceeded,
    MalformedProviderResponse,
    ProviderUnavailable,
)
from nosolear.domain.feedback import (
    FixChoice,
    SessionNotAnalyzed,
    SessionNotDaily,
    SessionNotFound,
    SkillOutcome,
    SkillState,
    choose_fixes,
    sanitize_explanation,
    template_explanation,
)
from nosolear.domain.profile import ALGO_VERSION, Profile
from nosolear.domain.taxonomy import Taxonomy
from nosolear.ports.feedback import (
    FallbackReason,
    FeedbackItem,
    FeedbackReport,
    FeedbackSource,
    FeedbackStore,
    SessionJobStatus,
    SessionObservationReader,
    SessionReader,
    SkillFeedback,
)
from nosolear.ports.plan import ProfileReader
from nosolear.ports.providers import Coach

_EVIDENCE_CAP = 300
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _no_profile(taxonomy: Taxonomy) -> Profile:
    """No profile yet (a new install). Fixes then rank by impact alone, and `as_of` is not read."""
    return Profile(
        as_of=_EPOCH,
        taxonomy_version=taxonomy.version,
        algo_version=ALGO_VERSION,
        pack_id="",
        entries=(),
    )


def _coach_inputs(fix: FixChoice) -> tuple[str, str]:
    quote = (fix.quote or fix.word or "")[:_EVIDENCE_CAP]
    context = (fix.context or fix.quote or fix.word or "")[:_EVIDENCE_CAP]
    return quote, context


def _reason_of(error: Exception) -> FallbackReason:
    if isinstance(error, CapExceeded):
        return "cap_exceeded"
    if isinstance(error, CapabilityMissing):
        return "capability_missing"
    return "provider_unavailable"


def _item(
    session_id: str,
    fix: FixChoice,
    *,
    message: str,
    model_text: str | None,
    source: FeedbackSource,
    reason: FallbackReason | None,
    item_id: str,
) -> FeedbackItem:
    return FeedbackItem(
        id=item_id,
        session_id=session_id,
        skill=fix.skill,
        error_key=fix.error_key,
        observation_id=fix.observation_id,
        attempt_id=fix.attempt_id,
        start_ms=fix.start_ms,
        end_ms=fix.end_ms,
        word=fix.word,
        message=message,
        model_text=model_text,
        source=source,
        fallback_reason=reason,
    )


def generate_feedback(
    *,
    session_id: str,
    sessions: SessionReader,
    jobs: SessionJobStatus,
    observations: SessionObservationReader,
    profiles: ProfileReader,
    feedback: FeedbackStore,
    coach: Coach,
    taxonomy: Taxonomy,
) -> FeedbackReport:
    kind = sessions.kind(session_id)
    if kind is None:
        raise SessionNotFound("No such session.")
    if kind != "daily":
        raise SessionNotDaily("Feedback is only made for a daily session.")
    if not jobs.analyzed(session_id):
        raise SessionNotAnalyzed("The session has no finished analysis yet.")

    profile = profiles.latest() or _no_profile(taxonomy)
    held = {item.skill: item for item in feedback.for_session(session_id)}
    # A stored fix keeps its key: a newer profile may rank another key first, but what was shown
    # stays as it was.
    outcomes = choose_fixes(
        session_observations=observations.for_session(session_id),
        profile=profile,
        taxonomy=taxonomy,
        pinned={skill: item.error_key for skill, item in held.items()},
    )
    written: list[FeedbackItem] = []
    # Set once the provider cannot serve this request; every later fix then gets a template with it.
    down: FallbackReason | None = None
    for outcome in outcomes:
        if outcome.state is not SkillState.FIX or outcome.fix is None:
            continue
        fix = outcome.fix
        existing = held.get(outcome.skill)
        if existing is not None and existing.source == "coach":
            continue
        if down is None:
            reason, down = _ask_coach(session_id, fix, coach, taxonomy, written)
            if reason is None:
                continue
        else:
            reason = down
        template = template_explanation(fix, taxonomy)
        written.append(
            _item(
                session_id,
                fix,
                message=template.message,
                model_text=template.model_text,
                source="template",
                reason=reason,
                item_id=uuid4().hex,
            )
        )
    if written:
        feedback.upsert(session_id, written)
    return _report(session_id, outcomes, feedback)


def _ask_coach(
    session_id: str,
    fix: FixChoice,
    coach: Coach,
    taxonomy: Taxonomy,
    written: list[FeedbackItem],
) -> tuple[FallbackReason | None, FallbackReason | None]:
    """Asks the coach about one fix. Returns (reason, down): reason is None when a coach item was
    written; down is set only when the provider cannot serve the rest of this request.

    A malformed reply costs only this fix, so the next fix is still asked.
    """
    quote, context = _coach_inputs(fix)
    try:
        raw = coach.explain(error_key=fix.error_key, quote=quote, context=context)
    except MalformedProviderResponse:
        return "invalid_output", None
    except (CapExceeded, ProviderUnavailable, CapabilityMissing) as error:
        reason = _reason_of(error)
        return reason, reason
    explanation = sanitize_explanation(raw, fix=fix, taxonomy=taxonomy)
    if explanation is None:
        return "invalid_output", None
    written.append(
        _item(
            session_id,
            fix,
            message=explanation.message,
            model_text=explanation.model_text,
            source="coach",
            reason=None,
            item_id=uuid4().hex,
        )
    )
    return None, None


def read_feedback(
    *,
    session_id: str,
    observations: SessionObservationReader,
    feedback: FeedbackStore,
    taxonomy: Taxonomy,
) -> FeedbackReport | None:
    """The stored feedback with each skill's state, or None when none was ever generated.

    No coach and no profile: the states come from the session's own observations, and the items
    are the stored ones. A later profile rebuild therefore cannot change what was shown.
    """
    if not feedback.for_session(session_id):
        return None
    outcomes = choose_fixes(
        session_observations=observations.for_session(session_id),
        profile=_no_profile(taxonomy),
        taxonomy=taxonomy,
    )
    return _report(session_id, outcomes, feedback)


def _report(
    session_id: str, outcomes: Sequence[SkillOutcome], feedback: FeedbackStore
) -> FeedbackReport:
    stored = {item.skill: item for item in feedback.for_session(session_id)}
    skills = tuple(
        SkillFeedback(
            skill=o.skill,
            state=o.state,
            item=stored.get(o.skill) if o.state is SkillState.FIX else None,
        )
        for o in outcomes
    )
    degraded = any(s.item is not None and s.item.source == "template" for s in skills)
    return FeedbackReport(session_id=session_id, skills=skills, degraded=degraded)
