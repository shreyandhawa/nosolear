# Security

## Scope

Nosolear is a local-only app: an API on your machine and a web app that talks to it. You bring your own Azure and Anthropic keys. There is no hosted service, so the things to protect are your keys (which spend your money and quota), your recordings, and your transcripts and profile.

## Single-user machines only

**Run Nosolear only on a single-user machine.** The API is bound to loopback and refuses other hosts, but until token mode arrives (planned for Phase 6) any local user on the same machine can call it, play back your recordings and spend your quota. On a shared machine, do not run it.

## Threat model in short

The full model is in section 15 of [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

- **Network:** the server binds 127.0.0.1 and refuses to start on anything else. Requests from non-loopback peers are refused, and Host and Origin checks defend against DNS rebinding and cross-site requests from web pages.
- **Secrets:** keys are held as secrets, scrubbed from logs and errors, never returned by the API, and live in `.env`, which is git-ignored. The repo holds no keys, not even example values.
- **Uploads:** recordings are accepted only as raw `audio/wav` bodies, capped at 10 MB and 120 seconds (checked from the frames actually received, not the declared length). Each file must be a 16-bit mono PCM WAV at a supported rate. Client file names and query strings are ignored, the server generates every stored name, and every path stays inside the data directory.
- **Data at rest:** recordings are stored as 0600 files under the 0700 data directory, never encrypted. Delete the data directory to remove them.
- **Supply chain:** exact pins and lockfiles, no `trust_remote_code`, and CI audits the lockfiles. Planned (Phase 0d): model files fetched at pinned revisions.
- **Local files:** the data directory is owner-only (0700, files 0600), and startup tightens a directory left looser by an earlier version. `nosolear doctor` warns when `.env` is readable by other users.
- **Untrusted text:** transcripts and coach output never build paths, SQL or shell commands.

## Reporting a vulnerability

Please report it privately, using the repository's private advisory form:

https://github.com/shreyandhawa/nosolear/security/advisories/new

## What not to put in a public issue

- API keys or tokens, even expired ones. If a key leaked, revoke it first.
- Recordings of your voice, or transcripts you would not want public.
- Contents of your `.env` or data directory.
