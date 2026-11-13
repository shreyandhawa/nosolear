# Nosolear

An open-source English speaking coach that runs on your own machine. You bring your own Azure Speech and Anthropic API keys and run it locally. There are no accounts, no hosting and no shared keys. It works for a speaker of any first language and aims at General American English.

It trains three skills:

- **Sounds**: per-sound pronunciation, stress and rhythm
- **On the spot**: building sentences in real time under a short time limit
- **Articulate**: expressing a full idea as point, reason, example

The daily loop takes about 15 minutes: speak for 60 seconds, get one fix per skill, shadow a model voice, and log misses to a personal error profile that picks tomorrow's practice.

## Status

The backend comes first. A first profile page exists, and the recording and scoring screens arrive in later phases (the main web UI is Phase 2). Today you can:

- seed a synthetic error profile with `make seed`, start `make api-dev` and `make web`, then open `/profile` at http://localhost:5173
- check your setup with `nosolear doctor`
- run the local API with `nosolear serve` (or `make api`)

Recording, scoring and the coach need the later phases. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and the build phases.

## Platforms

- **macOS on Apple Silicon** and **Linux on x86-64**: first-class, and tested in CI.
- **Windows**: use WSL2 and follow the Linux steps inside it.

## Prerequisites

Install these first. On macOS use [Homebrew](https://brew.sh); on Linux (and WSL2) use `apt` or your distribution's package manager.

- **Git**
- **[uv](https://docs.astral.sh/uv/)**: installs Python 3.14 and the API's dependencies
- **Node** at the version in `.node-version`, and **pnpm** at the version in the `packageManager` field of `apps/web/package.json`. Distribution packages for Node are usually far older, so on Linux and WSL2 install [fnm](https://github.com/Schniz/fnm), which reads `.node-version`, and run `fnm use --install-if-missing` in the repo root, then run `corepack enable` to get the pinned pnpm. If you use nvm instead, run `nvm install "$(cat .node-version)"`. On macOS, `brew install fnm` works the same way
- **make**
- **espeak-ng**: only for the `local` extra that arrives in Phase 0d; skip it for now

## Get your keys

Keys go in `.env` on your machine. Never paste a key into a chat, an issue or a pull request.

**Azure Speech** (pronunciation scoring and the model voice):

1. Create an Azure account. The free account asks for a non-prepaid card and a phone number for identity checks. A temporary $1 hold is placed and then released, and the F0 tier never bills.
2. Create a Speech resource on the **F0** (free) tier and note its key and region.
3. In Azure Cost Management, set a $1 budget alert as a safety net.

**Anthropic** (the AI coach):

1. Create an API key in the [Anthropic Console](https://console.anthropic.com), ideally in a workspace with a spend limit.

## Set up

```bash
git clone https://github.com/shreyandhawa/nosolear.git
cd nosolear
make setup
cp .env.example .env
chmod 600 .env
```

`make setup` installs the API and web dependencies and turns on the repository's git hooks. Then edit `.env`:

- `NOSOLEAR_AZURE_SPEECH_KEY` and `NOSOLEAR_AZURE_SPEECH_REGION`: from your Speech resource
- `NOSOLEAR_ANTHROPIC_API_KEY`: from the Console
- `NOSOLEAR_PACK`: optional language pack. The default is `neutral`; `nepali` adds weak starting guesses for Nepali first-language speakers

Every setting is listed, with its default, in `.env.example`. Keys and provider choices come only from the environment or `.env`.

## Check your setup

```bash
cd apps/api
uv run nosolear doctor
```

The report has one row per component: Azure Speech, Azure capabilities, Anthropic, transcriber, phone probe, language pack, data dir and usage. Each row shows one of these statuses, with the reason and the fix:

- **ready**: configured and usable
- **missing**: a required setting is not set
- **not installed**: an optional extra is not installed
- **not probed**: the live capability probe has not run
- **degraded**: it works, with a caveat

`nosolear doctor` is offline. It never prints a key, a fragment of one or its length. It exits 0 when nothing is missing, 1 when something is, and 2 when your settings are invalid. Until you add keys, Azure Speech and Anthropic show as missing, and so does the transcriber, which can use Azure or a local model from an extra. If the data dir row says `.env` is readable by other users, run `chmod 600 .env`. `nosolear doctor --probe` (live checks against the providers) arrives in Phase 0d.

## Run

```bash
make api    # the API on http://127.0.0.1:8000, restarts on code changes
make web    # the web app on http://localhost:5173
```

To try the profile page with synthetic data, run `make seed`, which writes under `data/dev`, then start the API with `make api-dev`. `make test`, `make lint` and `make test-live` run the tests, the linters and the live-provider tests (these last need your keys and are metered).

## Optional extras

- **Local speech models**: `uv sync --extra local` (wav2vec2 phone probe and faster-whisper, plus `espeak-ng`) and `uv sync --extra apple` (mlx-whisper on Apple Silicon) arrive in Phase 0d. Their download sizes will be added then.
- **Disk encryption**: your recordings and profile sit in `data/` unencrypted, so turn on full-disk encryption (FileVault on macOS, LUKS on Linux).

## What leaves your machine

- **Azure Speech** (your own resource and region): audio of each scored recording with its reference text; text to speak for the model voice; audio to transcribe only if you choose the `azure_stt` transcriber.
- **Anthropic** (your own key): transcripts, the prompt or reference text, and the error keys a request is about. Never audio.
- **Hugging Face**: requests for pinned model files on first use of a local model. No user data.

Nothing else leaves the machine. There is no telemetry, analytics, crash reporting or update check. See [PRIVACY.md](PRIVACY.md) for the full table and each provider's terms.

This repository is public. Recordings, the error profile and score history live only on the local machine under `data/`, which is git-ignored.

## Costs

Prices below were checked on 2026-11-11 and are subject to each provider's terms. Estimates assume daily use.

- **Azure Speech on F0**: free. Daily use takes about 1.5-2.5 of the 5 free audio hours a month and about 75k of the 500k free TTS characters a month. With `azure_stt` as the transcriber you come close to the cap, so a local transcriber is recommended.
- **Claude**: billed per token to your Anthropic account. At about 24k tokens a day, the default model (`claude-opus-5-5`) costs about $7 a month. Haiku 5.5 costs about $0.20.
- **Caps**: from Phase 0c and 0d, when the providers arrive, the app will reserve usage before every paid call and stop at your caps (nothing paid runs yet). Defaults: Azure at 4.5 audio hours and 450k TTS characters a month (90% of F0), Claude at 100k tokens a day. Change them with `NOSOLEAR_CAP_AZURE_AUDIO_HOURS`, `NOSOLEAR_CAP_AZURE_TTS_CHARS` and `NOSOLEAR_CAP_CLAUDE_TOKENS`.
- **Disk and RAM**: about 0.4 GB a month of audio; 3-5 GB of RAM while local speech models are loaded.

## Security

- **Run it on a single-user machine only.** Until the per-install token mode ships (Phase 6), the API has no login. It listens on 127.0.0.1, refuses to start on any other address, and answers only loopback peers, but any user or program on the same machine can reach it.
- **Never run the web dev server (or `vite preview`) with `--host`**, and never expose ports 5173 or 8000 to the network. `make web` pins the dev server, and `vite preview` of the built app, to `localhost` and refuses to start if `--host` is a non-loopback address, because the API trusts the dev proxy on this machine.
- Keep the data directory (`NOSOLEAR_DATA_DIR`, `data/` by default) under your home directory, not in a directory other users can write to such as `/tmp`.
- Keep keys in `.env` (git-ignored) and never in issues or chat. Keys are scrubbed from logs and never returned by the API.

Report a vulnerability through the private form described in [SECURITY.md](SECURITY.md).

## Licence

MIT: see [LICENSE](LICENSE). Third-party components, including model weights you may download, keep their own licences; see [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES). CrisperWhisper, an opt-in transcriber, has MIT code but non-commercial model weights (CC BY-NC 4.0), which the MIT licence does not cover. `espeak-ng` is GPL-3.0 or later and runs as a separate program.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
