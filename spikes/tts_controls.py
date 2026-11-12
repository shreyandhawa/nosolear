"""Synthesize TTS controls (S1/S2): one clip per calibration word, plus a READ_ALOUD sentence
at normal and -25% rate with WordBoundary events logged. Sequential, resumable."""
import json
from xml.sax.saxutils import escape

import azure.cognitiveservices.speech as speechsdk
import soundfile as sf

from common import DATA, log_usage, speech_config, with_backoff
from items import CALIBRATION, READ_ALOUD

PRIMARY_VOICE = "en-US-JennyNeural"
FALLBACK_VOICE = "en-US-AvaNeural"
TTS_DIR = DATA / "tts"
SENT_DIR = TTS_DIR / "sentences"
SENTENCE = READ_ALOUD[0]

_voice = PRIMARY_VOICE


def _ssml(text: str, rate: str | None = None) -> str:
    body = escape(text)
    if rate:
        body = f'<prosody rate="{rate}">{body}</prosody>'
    return (f"<speak version='1.0' xml:lang='en-US' xmlns='http://www.w3.org/2001/10/synthesis'>"
            f"<voice name='{_voice}'>{body}</voice></speak>")


def _synth(text: str, path, rate: str | None = None, boundaries: list | None = None) -> bool:
    """Synthesize to a 16 kHz mono WAV. Returns False if skipped (429s). Falls back to Ava once."""
    global _voice
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in (0, 1):
        ssml = _ssml(text, rate)
        cfg = speech_config()
        cfg.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm)
        synth = speechsdk.SpeechSynthesizer(cfg, speechsdk.audio.AudioOutputConfig(filename=str(path)))
        events: list = []
        synth.synthesis_word_boundary.connect(
            lambda e: events.append({"text": e.text, "offset_s": e.audio_offset / 1e7,
                                     "duration_s": e.duration.total_seconds()}))
        log_usage("azure_tts", 0, chars=len(ssml))
        result = with_backoff(lambda: synth.speak_ssml_async(ssml).get(), label=f"tts {path.name}")
        if result is None:
            del synth
            path.unlink(missing_ok=True)
            return False
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            del synth  # release the file handle
            if boundaries is not None:
                boundaries.extend(events)
            return True
        d = speechsdk.SpeechSynthesisCancellationDetails(result)
        del synth
        path.unlink(missing_ok=True)
        if attempt == 0 and _voice == PRIMARY_VOICE:
            print(f"{_voice} rejected ({d.error_code}); falling back to {FALLBACK_VOICE}")
            _voice = FALLBACK_VOICE
            continue
        raise RuntimeError(f"TTS failed for {path.name}: {d.error_code}")
    raise RuntimeError("unreachable")


def main() -> None:
    words = sorted({c.word for c in CALIBRATION})
    made = 0
    for w in words:
        out = TTS_DIR / f"{w}.wav"
        if out.exists():
            continue
        if _synth(w, out):
            made += 1
    print(f"word files synthesized this run: {made}; total: {len(list(TTS_DIR.glob('*.wav')))}")

    normal, slow = SENT_DIR / "ra1_normal.wav", SENT_DIR / "ra1_slow.wav"
    bfile = TTS_DIR / "word_boundaries.json"
    if not (normal.exists() and slow.exists() and bfile.exists()):
        events: list = []
        ok_normal = normal.exists() or _synth(SENTENCE, normal)
        ok_slow = _synth(SENTENCE, slow, rate="-25%", boundaries=events)
        if not (ok_normal and ok_slow):
            print("sentence clips incomplete (skipped after 429s, see skipped.jsonl); "
                  "no word_boundaries.json written, no slow_rate_ok claim. Rerun later.")
            return
        bfile.write_text(json.dumps({"voice": _voice, "rate": "-25%", "events": events}, indent=1, ensure_ascii=False))
    events = json.loads(bfile.read_text())["events"]
    d_normal, d_slow = sf.info(str(normal)).duration, sf.info(str(slow)).duration
    print(f"voice={_voice}")
    print(f"normal={d_normal:.2f}s slow={d_slow:.2f}s")
    print(f"word_boundary_events={len(events)}")
    print(f"slow_rate_ok={d_slow >= 1.2 * d_normal}")

if __name__ == "__main__":
    main()
