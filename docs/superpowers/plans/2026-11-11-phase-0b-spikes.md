# Phase 0b: Spikes S1–S3: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer the three questions in ARCHITECTURE §13 with measurements on the user's own voice:
- **S1:** what Azure's free tier actually returns.
- **S2:** which detector catches which error.
- **S3:** which local transcriber to use.

Then record the decisions that Phase 0c will be planned from.

**Architecture:** Throwaway scripts in `spikes/`, as their own `uv` project, so torch, transformers and the Azure SDK never enter `apps/api`'s lockfile. Recordings and raw provider output go to `data/spikes/` (git-ignored). Only the scripts and an aggregated results doc are committed. **Spike code is not test-driven and is never imported by `apps/`.** Phase 0c re-implements whatever survives, test-first.

**Tech Stack:**
- Python 3.14 and uv.
- `azure-cognitiveservices-speech==1.53.0`, `sounddevice==0.5.6`, `soundfile==0.14.0`.
- `torch==2.15.0`, `transformers==5.22.2`, `phonemizer==3.6.0` (needs `espeak-ng` from Homebrew).
- `mlx-whisper==0.4.3`, `python-dotenv`.

**Spec:** [docs/ARCHITECTURE.md](../../ARCHITECTURE.md), mainly §4, §5.1, §5.2, §11 and §13 (the spike table and its decision rules).

## Global Constraints

- **Azure budget:** at most 15 minutes of audio for the whole spike, against an F0 quota of 5 h/month. Every Azure call appends its audio seconds to `data/spikes/usage.jsonl`. The scripts abort once the total passes 900 s.
- **Requests:** F0 allows one concurrent request, so all Azure calls run sequentially. A 429 response is retried with exponential backoff (1, 2, 4, 8 s), then the item is skipped and logged.
- **Audio format:** every recording is 16 kHz mono 16-bit PCM WAV. Record at the device's native rate, then resample with `soundfile` and `numpy` before saving.
- **Privacy:**
  - Raw Azure JSON and transcripts of the user's speech stay in `data/spikes/` and are never committed.
  - The committed results doc holds only aggregate numbers and target words.
- **Phone symbols:** compare in Azure's en-US IPA. `spikes/phones.py` normalizes espeak and wav2vec2 symbols to Azure's (for example `r→ɹ`, and length marks dropped: `iː→i`). The map is extended whenever S1 shows a mismatch.
- **Decision rule (S2):** a detector is enabled for an error key only if it catches **≥ 80%** of the deliberate errors with **≤ 20%** false alarms on correct controls.
- **Commits:** no `Co-Authored-By` trailers and no Claude attribution. Work happens on the `p0b/spikes` branch, with one PR at the end.

## Review Focus

These are the failure modes most likely to produce a wrong decision. Each one is handled in its owning task.

1. **Mic sample rate isn't 16 kHz** (MacBook mics usually record at 48 kHz). Unresampled audio silently degrades both Azure and wav2vec2. Task 1 asserts that every saved file is `16000 Hz, 1 channel`.
2. **Symbol mismatch** between espeak, wav2vec2 and Azure: `ɹ`/`r`, `ɡ`/`g`, length marks, and `dʒ` written as one token versus two. Mismatches would read as false substitutions. Task 4 prints any unmapped symbol and fails loudly instead of guessing.
3. **TTS controls are native-like, so they understate false alarms on your careful-but-accented correct speech.** Task 4 reports a third column: the flag rate on your own "attempted correct" takes. The results doc states the caveat next to every enabled detector.
4. **The CrisperWhisper model is gated on Hugging Face, or too slow on MPS.** Task 2 records "unavailable" or the measured time, and the decision rule then falls back to mlx-whisper. Missing access is a result, not a blocker.
5. **F0 doesn't return prosody, or ignores `NBestPhonemeCount`.** Task 3 records which fields are present per request, instead of assuming. A missing field is a result.

---

### Task 0: Your one-time setup (about 20 minutes, done by you)

These steps need your accounts and credentials, so only you can do them. I'll provide an interactive checklist script when we start.

- [ ] **Azure:**
  1. Create a free account (card and phone for identity checks; a $1 hold is released).
  2. Create **one Speech resource with pricing tier F0** in region `eastus`.
  3. Add a **$1 budget alert** on the subscription.
  4. Put the key and region in the repo-root `.env` as `NOSOLEAR_AZURE_SPEECH_KEY` and `NOSOLEAR_AZURE_SPEECH_REGION`. The file is git-ignored.
- [ ] **Homebrew:** `brew install espeak-ng`.
- [ ] **Hugging Face, only if Task 2 reports the CrisperWhisper model as gated:** accept its license on huggingface.co while signed in, then run `hf auth login` in your own terminal.

Verify: `grep -c NOSOLEAR_AZURE_SPEECH .env` prints `2`, and `espeak-ng --version` prints a version.

---

### Task 1: Spike harness: recording sets, recorder, TTS controls

**Files:**
- Create: `spikes/pyproject.toml`, `spikes/README.md`, `spikes/common.py`, `spikes/items.py`, `spikes/record.py`, `spikes/tts_controls.py`, `spikes/phones.py`

**Interfaces:**
- **Produces, in `common.py`:**
  - `DATA = <repo>/data/spikes`.
  - `speech_config() -> speechsdk.SpeechConfig`, read from `.env`.
  - `log_usage(provider: str, seconds: float) -> None`. Raises `RuntimeError("Azure spike budget exceeded")` once the total exceeds 900 s.
  - `with_backoff(fn)`.
- **Produces, in `items.py`:**
  - `CalibrationItem(id, word, error_key, deliberate: bool, instruction)`.
  - `CALIBRATION: list[CalibrationItem]`. For each word below there is one "attempted correct" take and two deliberate-error takes:

    | Error key | Words |
    |---|---|
    | `sound.sub.v.w` | vest, very, van |
    | `sound.sub.w.v` | west, wine |
    | `sound.sub.f.p` | fan, fine, coffee |
    | `sound.sub.θ.t` | think, three, thanks |
    | `sound.sub.ð.d` | this, they |
    | `sound.sub.ʃ.s` | ship, she, shop |
    | `sound.sub.s.ʃ` | sip, see |
    | `sound.sub.z.dʒ` | zoo, zero |
    | `sound.sub.z.s` | zip, buzz |
    | `sound.ins.epenthesis_sC` | school, speak, street, sport |

    That's 26 words and 78 takes.
  - `READ_ALOUD: list[str]`: 5 sentences, each under 15 words, dense in the target sounds (written for this project).
  - `FREE_TALK_PROMPT = "Describe a place you love to visit and why."`
- **Produces, in `record.py`:**
  - CLI `uv run python record.py {calibration|read_aloud|free_talk}`.
  - For each item, it shows the instruction, records until Enter (60 s fixed for free talk), resamples to 16 kHz mono, and writes `data/spikes/rec/<set>/<id>.wav`.
  - It skips items that already exist, so you can resume.
- **Produces, in `tts_controls.py`:**
  - Synthesizes each calibration word with `en-US-JennyNeural` to `data/spikes/tts/<word>.wav` (16 kHz mono).
  - Also synthesizes one READ_ALOUD sentence at `<prosody rate="-25%">`, and logs whether `WordBoundary` events arrived, with their offsets.
- **Produces, in `phones.py`:** `normalize(symbol: str) -> str`, and `UnmappedSymbol(Exception)`.

- [ ] **Step 1: Implement the harness**
- [ ] **Step 2: Generate the TTS controls**

Run: `cd spikes && uv run python tts_controls.py`
Expected: 26 files in `data/spikes/tts/`, and the log prints `word_boundary_events=N (N>0)` and `slow_rate_ok=True`.

- [ ] **Step 3: You record, about 15 minutes**

```bash
cd spikes && uv run python record.py calibration
uv run python record.py read_aloud
uv run python record.py free_talk
```

Then: `uv run python -c "import soundfile as sf, glob; bad=[f for f in glob.glob('../data/spikes/rec/**/*.wav', recursive=True) if (sf.info(f).samplerate, sf.info(f).channels) != (16000, 1)]; print('bad:', bad)"`
Expected: `bad: []`, plus 78 + 5 + 1 recordings.

- [ ] **Step 4: Commit the scripts (no audio)**

```bash
git switch -c p0b/spikes && git add spikes && git commit -m "Add spike harness: recorder, items, TTS controls" && git push -u origin HEAD
```

---

### Task 2: S3, local transcription

**Files:** Create `spikes/s3_local_asr.py`

**Interfaces:**
- **Produces:** `data/spikes/s3/<engine>.json` for `crisperwhisper` and `mlx_whisper`, each holding `{available, load_s, transcribe_s, words: [{text, start, end}], filler_count}`.
  - **Fillers:** tokens matching `^(um+|uh+|er+|ah+|hmm+)$`, case-insensitive.
  - **CrisperWhisper:** transformers pipeline `automatic-speech-recognition`, model `nyrahealth/CrisperWhisper`, `return_timestamps="word"`, device `mps`.
  - **mlx-whisper:** `mlx_whisper.transcribe(path, path_or_hf_repo="mlx-community/whisper-large-v3-turbo", word_timestamps=True)`.
  - Time each engine twice: cold, then warm.

- [ ] **Step 1: Run on the 60-second free-talk clip**

Run: `uv run python s3_local_asr.py ../data/spikes/rec/free_talk/free_talk.wav`
Expected: a printed table of engine, available, cold s, warm s, words and fillers.

- [ ] **Step 2: Apply the rule.** Use CrisperWhisper if it's available and the warm run takes **≤ 20 s**. Otherwise use mlx-whisper, flagging filler counts as undercounted. Record the result in the results doc draft.
- [ ] **Step 3: Commit:** `git add spikes/s3_local_asr.py && git commit -m "Spike S3: local transcription timing" && git push`

---

### Task 3: S1, what Azure F0 returns

**Files:** Create `spikes/s1_azure.py`

**Interfaces:**
- **Produces:** raw JSON in `data/spikes/s1/` and a summary in `data/spikes/s1/summary.json`.
- **Config for every request:**
  - `PronunciationAssessmentConfig(grading_system=HundredMark, granularity=Phoneme, enable_miscue=<per mode>)`
  - `phoneme_alphabet="IPA"`, `nbest_phoneme_count=5`, `enable_prosody_assessment()`
  - language `en-US`
- **Three modes:**
  - **(a) Scripted:** single-shot per READ_ALOUD sentence, with reference text and miscue on.
  - **(b) Unscripted:** continuous recognition over the free-talk clip, with no reference text.
  - **(c) Transcribe then score:** continuous over the free-talk clip, with the S3 winner's transcript (fillers removed) as reference text and miscue off.
- **Summary fields per mode:**
  - `prosody_present`, `nbest_present`, `syllables_present`
  - `ipa_symbols_seen` (a sorted set)
  - `fillers_in_words`
  - `latency_s`, `audio_s`, `word_count`
  - for (b) and (c) only: word error rate against the S3 winner's transcript as reference.

- [ ] **Step 1: Run it.** Run: `uv run python s1_azure.py`
Expected: the summary is printed, and `usage.jsonl` totals under 300 s.

- [ ] **Step 2: Decide and record** in the results draft:
  1. Whether prosody is available on F0. If not, prosody keys wait for Phase 2.
  2. Whether n-best works.
  3. The IPA symbol set. Diff it against the taxonomy symbols in Phase 0a Task 3; any difference becomes a taxonomy v2 change in 0c.
  4. Which free-talk mode to use: (c) if its word list is at least as complete as (b), measured by WER against the local transcript; otherwise (b).
- [ ] **Step 3: Commit:** `git add spikes/s1_azure.py && git commit -m "Spike S1: Azure F0 pronunciation assessment fields" && git push`

---

### Task 4: S2, detector calibration

**Files:** Create `spikes/phone_probe.py`, `spikes/align.py`, `spikes/s2_calibrate.py`

**Interfaces:**
- **Produces, in `phone_probe.py`:**
  - `decode(path) -> list[str]`: greedy CTC decode with `facebook/wav2vec2-lv-60-espeak-cv-ft` on `mps`, normalized through `phones.normalize`.
  - `expected(word) -> list[str]`: `phonemizer.phonemize(word, language="en-us", backend="espeak", separator=Separator(phone=" "))`, normalized.
- **Produces, in `align.py`:**
  - `align(expected, produced) -> list[Op]`, where `Op = (kind: "match"|"sub"|"ins"|"del", e: str|None, p: str|None, index: int)`.
  - Needleman–Wunsch with costs: match 0, substitution 1, insertion and deletion 1. Ties prefer substitution.
- **Detection rules** (each returns `bool` per item):
  - **Azure, `sound.sub.E.P`:** for the first expected phoneme `E` in the word, the top n-best candidate is `P`.
  - **Probe, `sound.sub.E.P`:** the alignment has a `sub` op with `e == E` and `p == P`.
  - **Probe, `sound.ins.epenthesis_sC`:** the alignment has an `ins` op with a vowel `p` before the first expected `s`.
  - **Azure, `sound.ins.epenthesis_sC`:** marked "not supported", with no attempt.
- **Produces, in `s2_calibrate.py`:** `data/spikes/s2/results.csv` and a printed table per key × detector:
  - `hit_rate` on deliberate takes
  - `false_alarm_rate` on TTS controls
  - `flag_rate_on_attempted_correct` (informational)
  - `enabled` (per the rule)

- [ ] **Step 1: Sanity-check the probe on the TTS controls.** Run: `uv run python phone_probe.py ../data/spikes/tts/vest.wav`
Expected: it prints the decoded phones, which contain `v ɛ s t` after normalization. Any unmapped symbol raises `UnmappedSymbol` naming it.

- [ ] **Step 2: Run the calibration.** Run: `uv run python s2_calibrate.py`
Expected: a table covering all 10 keys and 2 detectors (Azure n/a for epenthesis), and `usage.jsonl` under 900 s in total.

- [ ] **Step 3: Commit:** `git add spikes && git commit -m "Spike S2: detector calibration" && git push`

---

### Task 5: Results doc and architecture updates

**Files:**
- Create: `docs/spikes/2026-11-phase-0-results.md`
- Modify: `docs/ARCHITECTURE.md` (§4 detectors per key, §5.1 transcriber choice, §4 free-talk scoring mode, §6.2 phone symbols if S1 changed them)

- [ ] **Step 1: Write the results doc.**
  - Sections: S1, S2 and S3, each with the measurement, the decision and the caveats.
  - Then a **"Changes for Phase 0c"** list: the taxonomy v2 symbol map, the detector set per key, the transcriber, the free-talk mode and the prosody availability.
  - Aggregate numbers only; no transcripts of your speech.
- [ ] **Step 2: Update ARCHITECTURE.md** to match the decisions.
- [ ] **Step 3: Open one PR, then merge once CI (hygiene) is green and you've read the results.**

```bash
git add docs && git commit -m "Record Phase 0 spike results and decisions" && git push
gh pr create --title "Phase 0 spikes: results and decisions" --fill
```

## Done when

- The results doc answers S1–S3, with each decision tied to a measurement.
- ARCHITECTURE.md reflects those decisions.
- Total Azure usage is under 15 minutes.
- The Phase 0c plan (baseline end to end: recording UI, real adapters, analysis pipeline, baseline report) can be written from the results.
