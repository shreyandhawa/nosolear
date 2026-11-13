"""Azure pronunciation assessment: the raw `PronunciationScorer` (ARCHITECTURE.md section 5.1).

A clip of at most `MAX_SCRIPTED_SECONDS` with reference text is scored once, with miscue on. A
longer clip with reference text is scored in continuous mode, miscue off. A clip without
reference text is scored unscripted, in continuous mode. The phoneme alphabet is IPA, with five
n-best phonemes and prosody on, so the result is the same JSON shape in every mode.
"""

import json
from pathlib import Path

from nosolear.adapters.azure_speech import AzureSpeech, RecognitionRequest, wav_seconds
from nosolear.domain.budget import Provider
from nosolear.domain.results import parse_azure_pa
from nosolear.domain.speech import (
    MAX_SCRIPTED_SECONDS,
    PronunciationAssessment,
    RawResult,
    ScoringMode,
)

ADAPTER = "azure_pa"
ADAPTER_VERSION = 1
NBEST_PHONEME_COUNT = 5
TIMEOUT_BASE_S = 30
TIMEOUT_PER_AUDIO_SECOND = 2


def scoring_mode(reference_text: str | None, duration_s: float) -> ScoringMode:
    if not reference_text:
        return ScoringMode.UNSCRIPTED
    return ScoringMode.SCRIPTED if duration_s <= MAX_SCRIPTED_SECONDS else ScoringMode.CONTINUOUS


def pronunciation_config_json(reference_text: str | None, mode: ScoringMode) -> str:
    return json.dumps(
        {
            "ReferenceText": reference_text or "",
            "GradingSystem": "HundredMark",
            "Granularity": "Phoneme",
            "EnableMiscue": mode is ScoringMode.SCRIPTED,
            "PhonemeAlphabet": "IPA",
            "NBestPhonemeCount": NBEST_PHONEME_COUNT,
            "EnableProsodyAssessment": True,
        }
    )


class AzurePronunciationScorer:
    layer = "raw"

    def __init__(self, speech: AzureSpeech, *, locale: str) -> None:
        self._speech = speech
        self._locale = locale

    def score(self, wav: Path, *, reference_text: str | None) -> PronunciationAssessment:
        duration = wav_seconds(wav)
        mode = scoring_mode(reference_text, duration)
        request = RecognitionRequest(
            wav=wav,
            locale=self._locale,
            continuous=mode is not ScoringMode.SCRIPTED,
            pronunciation_json=pronunciation_config_json(reference_text, mode),
            word_timestamps=False,
            timeout_s=TIMEOUT_PER_AUDIO_SECOND * duration + TIMEOUT_BASE_S,
        )
        outcome = self._speech.recognize(request)
        payload = {
            "mode": mode.value,
            "reference_text": reference_text,
            "results": list(outcome.results),
        }
        return parse_azure_pa(
            RawResult(
                provider=Provider.AZURE.value,
                provider_version=self._speech.version,
                adapter=ADAPTER,
                adapter_version=ADAPTER_VERSION,
                payload=payload,
            )
        )
