---
version: 1
slug: "apps-web-src-app-router-tsx"
primary_target: "apps/web/src/app/router.tsx"
related_targets: ["apps/web/src/features"]
---

# Studio desk: the Nosolear app screens

Scope: every app screen (Setup, Calibration, Baseline and report, Today, Progress). Mode: Operate. Build path: code-led (direction pinned by the owner's brief; no concept roll).

Audience and job: the owner, alone at a laptop, does one take at a time: listen to the model, press the microphone, speak, read the fix.

## Direction contract

seed: none (direction pinned by the owner's brief)

THESIS: A pronunciation key that listens. A quiet studio desk: paper columns either side of an ink stage holding one glowing 3D microphone, which is the record control. Refuses the SaaS dashboard of cards, sidebars and stat tiles.

OWN-WORLD: Paper oklch(94.4% 0.0144 84.6) sides, Ink oklch(21.4% 0.0119 167.3) stage and text, On air oklch(66.6% 0.2237 34.3) for recording and the one primary action (fill only, never text on paper), Phosphor oklch(88.1% 0.1237 167.9) only for the microphone's halo and rim light. Gentium Book Plus for titles and every phonetic symbol; Schibsted Grotesk for the interface, tabular figures. Hairline rules, no cards inside cards, status by dot shape and words.

FIRST VIEWPORT: one fixed eight-slot grid (36/44/20): Navigation; Title, Media, Text left; the microphone stage centre, full height; Card, Text, CTA right. Every state swaps content, never layout.

STORY: the owner sees what to say (large, phonetic), hears it, presses the microphone, watches the glow follow the voice, then reads one fix per skill beside the clip.

SIGNATURE: the microphone. Halo size and brightness are the live input level; a thin arc fills over the time limit; slats light bottom to top with the analysis job's real progress.

RISK: the 3D scene must never block recording. Lazy-loaded, flat silhouette fallback, render on demand.
