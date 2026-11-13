"""Azure speech-to-text: the raw `Transcriber` (ARCHITECTURE.md section 5).

Continuous recognition with word timestamps and detailed output. Profanity is passed through as
said (`ProfanityOption.Raw`, set in the SDK backend), so the transcript stays verbatim.
"""

from pathlib import Path

from nosolear.adapters.azure_speech import AzureSpeech, RecognitionRequest, wav_seconds
from nosolear.domain.budget import Provider
from nosolear.domain.results import parse_azure_stt
from nosolear.domain.speech import RawResult, Transcript

ADAPTER = "azure_stt"
ADAPTER_VERSION = 1
TIMEOUT_BASE_S = 30
TIMEOUT_PER_AUDIO_SECOND = 2


class AzureTranscriber:
    layer = "raw"

    def __init__(self, speech: AzureSpeech, *, locale: str) -> None:
        self._speech = speech
        self._locale = locale

    def transcribe(self, wav: Path) -> Transcript:
        duration = wav_seconds(wav)
        request = RecognitionRequest(
            wav=wav,
            locale=self._locale,
            continuous=True,
            pronunciation_json=None,
            word_timestamps=True,
            timeout_s=TIMEOUT_PER_AUDIO_SECOND * duration + TIMEOUT_BASE_S,
        )
        outcome = self._speech.recognize(request)
        return parse_azure_stt(
            RawResult(
                provider=Provider.AZURE.value,
                provider_version=self._speech.version,
                adapter=ADAPTER,
                adapter_version=ADAPTER_VERSION,
                payload={"results": list(outcome.results)},
            )
        )
