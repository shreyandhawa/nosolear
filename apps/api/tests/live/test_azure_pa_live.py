from collections.abc import Callable
from pathlib import Path

import pytest

from nosolear.adapters.azure_pa import AzurePronunciationScorer
from nosolear.adapters.azure_speech import AzureSpeech
from nosolear.api.deps import paid_scorer
from nosolear.budget.meter import Meter
from nosolear.settings import Settings


@pytest.mark.live
def test_tts_sentence_scores_high_and_reports_tier(
    live_azure: AzureSpeech,
    live_settings: Settings,
    live_meter: Meter,
    tts_clip: Callable[..., Path],
):
    text = "The vest is in the van by the west wall."
    scorer = paid_scorer(
        AzurePronunciationScorer(live_azure, locale=live_settings.azure_locale), live_meter
    )
    a = scorer.score(tts_clip(text), reference_text=text)
    assert len(a.words) == 10 and a.accuracy is not None and a.accuracy >= 80
    print(f"n-best={a.has_nbest} prosody={a.has_prosody}")  # recorded in HANDOFF for the owner
