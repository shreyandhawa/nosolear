# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

One person, the owner: a speaker of another first language practising General American English for about 15 minutes a day, alone at a laptop with a microphone. The app is laptop first (1280 px and wider); phone access comes later.

## Product Purpose

An English speaking coach that runs on the owner's own machine. It trains three skills: Sounds (per-sound pronunciation, stress and rhythm), On the spot (building sentences in real time), and Articulate (point, reason, example). The daily loop: speak for 60 seconds, get one fix per skill, shadow a model voice, and log misses to a personal error profile that picks tomorrow's practice. The first run is setup, calibration on the owner's voice, then a baseline.

## Positioning

It learns one speaker's own error profile (calibrated detectors, measured miss rates with uncertainty) and practises exactly those errors, with every score traced to a recorded clip.

## Operating Context

Runs locally from `make app` at http://127.0.0.1:8000. No accounts, no hosting, no telemetry. Nothing leaves the machine except calls the owner's own Azure Speech and Anthropic keys make, metered against monthly and daily caps.

## Capabilities and Constraints

- Every user action happens in the web app; the CLI is for debugging.
- Error keys use phonetic symbols (ʌ, æ, ɹ, θ, ð).
- Feedback can fall back to a template when the coach is capped or unavailable, and a skill can be "not scored today".
- Paid calls happen only on an explicit POST; no page view spends quota.

## Brand Commitments

Name: Nosolear. Voice: plain, direct, no marketing copy.

## Evidence on Hand

Real content only: calibration words and respellings (`content/calibration/items.toml`), the baseline protocol (`content/baseline/protocol.json`), the error taxonomy, and the owner's own recordings and scores. No testimonials, statistics or invented numbers.

## Product Principles

- One task on screen at a time; the microphone is always the way to act.
- Every number shown comes from the API.
- Honest state: provisional, not scored, template and blocked are shown, never hidden.
- Nothing leaves the machine that the owner did not start.

## Accessibility & Inclusion

Keyboard reaches everything, with Space as the record shortcut. WCAG AA text contrast. Recording state is never shown by colour alone.
