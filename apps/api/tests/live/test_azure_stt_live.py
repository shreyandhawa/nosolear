from collections.abc import Callable
from pathlib import Path

import pytest
from textmetrics import word_error_rate

from nosolear.adapters.azure_pa import AzurePronunciationScorer
from nosolear.adapters.azure_speech import AzureSpeech
from nosolear.adapters.azure_stt import AzureTranscriber
from nosolear.api.deps import paid_scorer, paid_transcriber
from nosolear.budget.meter import Meter

FREE_TALK_SAMPLE = (
    "Every morning I walk the same route to the small bakery on the corner. The street is "
    "quiet before eight, and the air smells of cut grass and fresh bread. Last week the "
    "bakery owner, a patient woman named Rosa, asked whether I was training for a race. I "
    "laughed and told her that I was only trying to learn English properly, one "
    "conversation at a time. She nodded as if that were a very reasonable plan. We talked "
    "about her grandmother, who grew up in a village where everyone knew each other's "
    "business, and about the new library that opened across the river. The library has a "
    "reading room with tall windows, and on rainy afternoons it fills with students who "
    "spread their notes across the wooden tables. I have started going there twice a week."
    " I bring a notebook, write down new words, and read the local newspaper aloud until "
    "the sentences feel natural. Rosa says that progress is measured in small habits "
    "rather than dramatic leaps."
)


@pytest.mark.live
def test_transcribes_tts_audio(
    live_azure: AzureSpeech, live_meter: Meter, tts_clip: Callable[..., Path]
):
    text = "Yesterday I walked to the market and bought three green apples."
    transcriber = paid_transcriber(AzureTranscriber(live_azure, locale="en-US"), live_meter)
    t = transcriber.transcribe(tts_clip(text))
    assert word_error_rate(text, t.text) <= 0.15 and len(t.words) >= 9


@pytest.mark.live
def test_free_talk_scoring_modes(
    live_azure: AzureSpeech, live_meter: Meter, tts_clip: Callable[..., Path]
):
    """§4: compare unscripted against transcribe-then-score on about 60 s of TTS free talk."""
    clip = tts_clip(FREE_TALK_SAMPLE)
    scorer = paid_scorer(AzurePronunciationScorer(live_azure, locale="en-US"), live_meter)
    transcript = paid_transcriber(
        AzureTranscriber(live_azure, locale="en-US"), live_meter
    ).transcribe(clip)
    unscripted = scorer.score(clip, reference_text=None)
    continuous = scorer.score(clip, reference_text=transcript.text)
    for name, a in [("unscripted", unscripted), ("transcribe_then_score", continuous)]:
        print(name, len(a.words), a.accuracy, sum(w.error_type != "None" for w in a.words))
    assert unscripted.words and continuous.words
