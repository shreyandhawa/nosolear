"""`AzureTranscriber` through the fake backend: continuous mode with word timestamps."""

from provider_fakes import FakeSpeechBackend
from pydantic import SecretStr
from security.planted import PLANTED_AZURE_KEY
from wavs import write_wav

from adapters.azure_payloads import stt_phrase
from nosolear.adapters.azure_speech import AzureSpeech, RecognitionOutcome
from nosolear.adapters.azure_stt import AzureTranscriber


def test_request_is_continuous_with_word_timestamps_and_result_is_tagged(tmp_path):
    backend = FakeSpeechBackend(
        recognition=[
            RecognitionOutcome(
                results=(stt_phrase("Hello there.", [("Hello", 0, 400, 0.9)]),),
                cancellation=None,
            )
        ]
    )
    speech = AzureSpeech(key=SecretStr(PLANTED_AZURE_KEY), region="eastus", backend=backend)
    wav = write_wav(tmp_path / "a.wav", 2.0)
    transcript = AzureTranscriber(speech, locale="en-US").transcribe(wav)
    request = backend.calls[0]
    assert request.continuous and request.word_timestamps
    assert request.pronunciation_json is None and request.locale == "en-US"
    assert transcript.text == "Hello there."
    assert transcript.raw.adapter == "azure_stt"
    assert transcript.raw.provider == "azure"
