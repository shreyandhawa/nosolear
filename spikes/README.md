# Phase 0b spikes

Throwaway measurement scripts (own uv project, never imported by `apps/`). Output goes to `../data/spikes/` (git-ignored; never commit audio or transcripts).

```bash
cd spikes && uv sync
uv run python tts_controls.py                 # 26 TTS word controls + slow-rate sentence (needs ../.env)
uv run python record.py calibration --list    # inspect a set without touching the mic
uv run python record.py calibration           # then read_aloud, free_talk; resumable
```

- `common.py`: paths, Azure config from `../.env`, usage/budget log (900 s recognition cap), 429 backoff, numpy resampler to 16 kHz.
- `items.py`: calibration words (78 takes), read-aloud sentences, free-talk prompt.
- `phones.py`: espeak / wav2vec2 -> Azure en-US IPA; raises `UnmappedSymbol` on unknown symbols.
- `phonemizer` needs `PHONEMIZER_ESPEAK_LIBRARY=/opt/homebrew/lib/libespeak-ng.1.dylib` on this machine.
