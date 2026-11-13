"""Oracle doubles for the raw speech ports: what is "said" can be recovered from the clip itself.

The n-th distinct text spoken through `speech_synthesizer` is a seeded-noise clip of 1000 + 10·n
ms, so the other ports recover the text from the WAV they are given. Azure and espeak payloads
are built with the test payload builders and parsed by the real parsers, so the stored raw JSON
re-parses to the same result. Import as `from oracle_voice import OracleVoice`.
"""

import wave
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from adapters.azure_payloads import pa_phoneme, pa_phrase, pa_word
from wavs import make_wav

from nosolear.domain.phones import AZURE_PHONES
from nosolear.domain.results import parse_azure_pa, parse_local_transcript, parse_phone_probe
from nosolear.domain.speech import (
    PhoneProbeResult,
    PronunciationAssessment,
    RawResult,
    SynthesizedAudio,
    Transcript,
)

BASE_MS: Final = 1000
STEP_MS: Final = 10
VOICE: Final = "en-US-AvaNeural"
_DIGRAPHS: Final = {"th": "θ", "sh": "ʃ", "ch": "tʃ", "ng": "ŋ"}
_LETTERS: Final = {"g": "ɡ", "r": "ɹ", "c": "k", "q": "k", "y": "j"}
_VOWELS: Final = frozenset("aeiou")


def phones_of(word: str) -> list[str]:
    """A small grapheme-to-phone map: digraphs first, every vowel letter as schwa."""
    text = "".join(ch for ch in word.lower() if ch.isalpha())
    phones: list[str] = []
    i = 0
    while i < len(text):
        pair = text[i : i + 2]
        if pair in _DIGRAPHS:
            phones.append(_DIGRAPHS[pair])
            i += 2
            continue
        ch = text[i]
        if ch in _VOWELS:
            phones.append("ə")
        else:
            phone = _LETTERS.get(ch, ch)
            if phone in AZURE_PHONES:
                phones.append(phone)
        i += 1
    return phones


class _Port:
    layer = "raw"

    def __init__(self, voice: OracleVoice, name: str) -> None:
        self._voice = voice
        self._name = name

    def _enter(self) -> None:
        self._voice.calls[self._name] += 1
        if self._voice.failure is not None:
            raise self._voice.failure


class _Speech(_Port):
    def __init__(self, voice: OracleVoice) -> None:
        super().__init__(voice, "speech_synthesizer")

    def synthesize(self, text: str, *, rate_percent: int) -> SynthesizedAudio:
        del rate_percent
        self._enter()
        n = self._voice.id_for(text)
        seconds = (BASE_MS + STEP_MS * n) / 1000
        return SynthesizedAudio(
            wav=make_wav(seconds, freq=None),
            word_timings=(),
            voice=VOICE,
            billed_chars=len(text),
        )


class _Scorer(_Port):
    def __init__(self, voice: OracleVoice) -> None:
        super().__init__(voice, "scorer")

    def score(self, wav: Path, *, reference_text: str | None) -> PronunciationAssessment:
        self._enter()
        spoken = self._voice.spoken_text(wav)
        text = reference_text if reference_text is not None else spoken
        words: list[dict[str, object]] = []
        offset = 0
        for index, word in enumerate(text.split()):
            phonemes = []
            for expected in phones_of(word):
                produced = self._voice.user_errors.get(expected, expected)
                if produced == expected:
                    entry = pa_phoneme(
                        expected, 95, nbest=[(expected, 95)], offset_ms=offset, duration_ms=50
                    )
                else:
                    entry = pa_phoneme(
                        expected,
                        30,
                        nbest=[(produced, 80), (expected, 40)],
                        offset_ms=offset,
                        duration_ms=50,
                    )
                phonemes.append(entry)
                offset += 50
            words.append(
                pa_word(
                    word,
                    90,
                    offset_ms=offset - 50 * len(phonemes),
                    duration_ms=50 * len(phonemes),
                    phonemes=phonemes,
                )
            )
            del index
        payload: dict[str, object] = {
            "mode": "scripted" if reference_text is not None else "unscripted",
            "reference_text": reference_text,
            "results": [pa_phrase(words)],
        }
        return parse_azure_pa(
            RawResult(
                provider="azure",
                provider_version="oracle",
                adapter="azure_pa",
                adapter_version=1,
                payload=payload,
            )
        )


class _Probe(_Port):
    def __init__(self, voice: OracleVoice) -> None:
        super().__init__(voice, "probe")

    def probe(self, wav: Path, *, reference_text: str) -> PhoneProbeResult:
        del wav
        self._enter()
        expected_words = [phones_of(word) for word in reference_text.split()]
        heard = [
            self._voice.user_errors.get(phone, phone) for word in expected_words for phone in word
        ]
        payload: dict[str, object] = {
            "espeak_ipa": " ".join("_".join(word) for word in expected_words),
            "espeak_version": "oracle",
            "heard_tokens": heard,
            "model": {"repo_id": "oracle", "revision": "oracle"},
        }
        return parse_phone_probe(
            RawResult(
                provider="local",
                provider_version="oracle",
                adapter="wav2vec2_espeak",
                adapter_version=1,
                payload=payload,
            )
        )


class _Transcriber(_Port):
    def __init__(self, voice: OracleVoice) -> None:
        super().__init__(voice, "transcriber")

    def transcribe(self, wav: Path) -> Transcript:
        self._enter()
        spoken = self._voice.spoken_text(wav)
        words = [
            {
                "word": word,
                "start": (600 + 400 * index) / 1000,
                "end": (1000 + 400 * index) / 1000,
                "probability": 0.9,
            }
            for index, word in enumerate(spoken.split())
        ]
        payload: dict[str, object] = {
            "engine": "faster_whisper",
            "model": {"repo_id": "oracle", "revision": "oracle"},
            "fillers_kept": False,
            "text": spoken,
            "words": words,
        }
        return parse_local_transcript(
            RawResult(
                provider="local",
                provider_version="oracle",
                adapter="faster_whisper",
                adapter_version=1,
                payload=payload,
            )
        )


class OracleVoice:
    """Speech doubles that know what was said. Set `user_errors` to make the speaker substitute
    a phone everywhere (for example `{"v": "w"}`). `calls` counts each port's calls, and
    `fail_all` makes every later call raise."""

    def __init__(self, user_errors: Mapping[str, str] | None = None) -> None:
        self.user_errors: dict[str, str] = dict(user_errors or {})
        self.calls: Counter[str] = Counter()
        self.failure: Exception | None = None
        self._ids: dict[str, int] = {}
        self._texts: dict[int, str] = {}
        self.speech_synthesizer = _Speech(self)
        self.scorer = _Scorer(self)
        self.transcriber = _Transcriber(self)
        self.probe = _Probe(self)

    def fail_all(self, exc: Exception) -> None:
        self.failure = exc

    def id_for(self, text: str) -> int:
        if text not in self._ids:
            n = len(self._ids) + 1
            self._ids[text] = n
            self._texts[n] = text
        return self._ids[text]

    def spoken_text(self, wav: Path) -> str:
        with wave.open(str(wav), "rb") as handle:
            ms = handle.getnframes() * 1000 // handle.getframerate()
        return self._texts[(ms - BASE_MS) // STEP_MS]
