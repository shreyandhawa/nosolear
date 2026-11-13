"""Live coach calls: they spend the Max token budget, so they run only when the owner asks
(`make test-live`). Never run in CI or unit tests."""

import pytest

from nosolear.adapters.claude_coach import ClaudeCoach
from nosolear.api.deps import paid_coach
from nosolear.budget.meter import Meter
from nosolear.domain.coach import (
    MAX_EXPLANATION_CHARS,
    MAX_MODEL_TEXT_CHARS,
    CoachTask,
    coach_keys,
    quote_in_transcript,
)
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as TAX
from nosolear.settings import Settings

KEYS = coach_keys(TAX, CoachTask.QUICK_ANSWERS)


@pytest.mark.live
def test_finds_and_quotes_a_tense_error(
    require_anthropic, live_settings: Settings, live_meter: Meter
):
    transcript = "Yesterday I go to the market and buy three apple."
    raw = ClaudeCoach(
        api_key=live_settings.anthropic_api_key,
        model=live_settings.coach_model,
        taxonomy=TAX,
    )
    coach = paid_coach(raw, live_meter, taxonomy=TAX)
    analysis = coach.analyze(
        task=CoachTask.QUICK_ANSWERS,
        prompt_text="What did you do yesterday?",
        transcript=transcript,
        allowed_keys=KEYS,
    )
    assert {"grammar.verb_tense", "grammar.plural"} & {f.error_key for f in analysis.findings}
    assert all(quote_in_transcript(f.quote or "", transcript) for f in analysis.findings)
    assert analysis.tokens_used > 0


@pytest.mark.live
def test_explains_a_tense_error(require_anthropic, live_settings: Settings, live_meter: Meter):
    raw = ClaudeCoach(
        api_key=live_settings.anthropic_api_key,
        model=live_settings.coach_model,
        taxonomy=TAX,
    )
    explanation = paid_coach(raw, live_meter, taxonomy=TAX).explain(
        error_key="grammar.verb_tense",
        quote="I go",
        context="Yesterday I go to the market.",
    )
    assert explanation.message and explanation.model_text
    assert len(explanation.message) <= MAX_EXPLANATION_CHARS
    assert len(explanation.model_text) <= MAX_MODEL_TEXT_CHARS
