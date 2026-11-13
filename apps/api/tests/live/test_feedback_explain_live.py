"""The real coach explaining three fixes through generate_feedback. It spends the Max budget, so it
runs only when the owner asks (`make test-live`). Never run in CI or in the unit tests."""

import unicodedata

import pytest
from factories import NOW, mk
from fakes import (
    FakeFeedbackStore,
    FakeProfileReader,
    FakeSessionJobStatus,
    FakeSessionObservations,
    FakeSessionReader,
)

from nosolear.adapters.claude_coach import ClaudeCoach
from nosolear.api.deps import paid_coach
from nosolear.app.generate_feedback import generate_feedback
from nosolear.budget.meter import Meter
from nosolear.domain.coach import MAX_EXPLANATION_CHARS, MAX_MODEL_TEXT_CHARS
from nosolear.domain.feedback import SkillState
from nosolear.domain.observations import Outcome
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as TAX
from nosolear.domain.taxonomy import Detector
from nosolear.ports.feedback import StoredObservation
from nosolear.settings import Settings


@pytest.mark.live
def test_real_coach_explains_three_fixes_and_stores_sanitized_items(
    require_anthropic, live_settings: Settings, live_meter: Meter
):
    raw = ClaudeCoach(
        api_key=live_settings.anthropic_api_key,
        model=live_settings.coach_model,
        taxonomy=TAX,
    )
    coach = paid_coach(raw, live_meter, taxonomy=TAX)
    observations = [
        StoredObservation(
            id=1,
            observation=mk(
                "sound.sub.v.w",
                Outcome.MISS,
                NOW,
                detector=Detector.AZURE_PA,
                attempt_id="a1",
                evidence={"word": "very", "start_ms": 100, "end_ms": 300},
            ),
        ),
        StoredObservation(
            id=2,
            observation=mk(
                "fluency.filler",
                Outcome.MISS,
                NOW,
                detector=Detector.ASR_METRICS,
                attempt_id="a1",
                evidence={"text": "um I think it is good", "start_ms": 400, "end_ms": 900},
            ),
        ),
        StoredObservation(
            id=3,
            observation=mk(
                "grammar.article",
                Outcome.MISS,
                NOW,
                detector=Detector.COACH,
                attempt_id="a1",
                evidence={"quote": "go to market"},
            ),
        ),
    ]
    report = generate_feedback(
        session_id="live",
        sessions=FakeSessionReader({"live": "daily"}),
        jobs=FakeSessionJobStatus({"live": 0}),
        observations=FakeSessionObservations({"live": observations}),
        profiles=FakeProfileReader(None),
        feedback=FakeFeedbackStore(),
        coach=coach,
        taxonomy=TAX,
    )
    assert report.degraded is False
    for skill in report.skills:
        assert skill.state is SkillState.FIX
        assert skill.item is not None
        assert skill.item.source == "coach"
        assert 0 < len(skill.item.message) <= MAX_EXPLANATION_CHARS
        assert all(unicodedata.category(ch) not in ("Cc", "Cf") for ch in skill.item.message)
        if skill.item.model_text is not None:
            assert len(skill.item.model_text) <= MAX_MODEL_TEXT_CHARS
