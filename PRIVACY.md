# Privacy

Nosolear runs on your machine. It has no accounts and no server of ours. It talks to three outside services, and only the ones you set up.

## What leaves your machine

| Destination | What is sent | When |
|---|---|---|
| Azure Speech (your own resource and region) | Audio of each scored recording (16 kHz WAV) with its reference text | Scoring, calibration, the baseline and drills |
| | Audio of recordings to transcribe | Only when the transcriber is `azure_stt` |
| | Text to speak, as SSML | Text-to-speech cache misses: model voice, calibration controls, probe and speed-check clips |
| | Synthesized audio only, never your voice | `nosolear doctor --probe` and `make test-live` |
| Anthropic (your own key) | Transcripts, the item text (prompt or reference), and the error keys the request is about | Coach calls. Never audio |
| Hugging Face | Requests for pinned model files; no user data | First use of a local model (`local` or `apple` extra) |

The Azure Speech SDK 1.53.0 has its own telemetry code. Its Python API, which Nosolear uses, exposes no switch for it, so Nosolear cannot turn it off from its side; this was checked on that version and is not something Nosolear adds.

**Nothing else leaves the machine.** There is no telemetry, analytics, crash reporting or update check. The package managers (`uv`, `pnpm`) contact their registries only when you install or update.

## Where your data lives

Recordings, raw provider results, transcripts, observations, your profile and its history all stay in the data directory. Deleting that directory deletes all of it.

Recordings are stored unencrypted. Turn on full-disk encryption (FileVault on macOS, LUKS on Linux).

## The providers' own terms

Each provider's data-handling terms apply to what it receives:

- Microsoft: [Data, privacy, and security for Speech to text](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/speech-service/speech-to-text/data-privacy-security)
- Anthropic: [Commercial Terms of Service](https://www.anthropic.com/legal/commercial-terms) and the [Privacy Center for commercial customers](https://privacy.claude.com/en/collections/10663361-commercial-customers)
- Hugging Face: [Privacy Policy](https://huggingface.co/privacy)

If you change what Nosolear sends or add a destination, this file must change in the same pull request.
