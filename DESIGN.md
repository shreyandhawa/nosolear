# Design

The Nosolear app is a quiet studio desk: paper on both sides, an ink stage in the middle, and one glowing 3D microphone on it, which is the record control. It should read like a well-made dictionary and a recording booth, never a dashboard. Product truth lives in PRODUCT.md.

## Layout

One layout for every screen (`shared/ui/Desk.tsx`), under a 56 px navigation bar. Columns are 36 / 44 / 20 (`minmax(0, fr)`, so long tokens never widen the page). The left column holds Title (the top half), then Media and Text at 75% of its width. The centre is the Ink stage with the microphone, full height. The right column holds Card and Text, which share the height, and a short CTA bar. States swap content, never layout, and the microphone never moves. Designed at 1440 by 900, holds from 1280 to 1728, and degrades without breaking at 1024. There is no phone layout yet.

## Colour

Tokens are in `index.css` `@theme`, in OKLCH.

| Token | Value | Use |
|---|---|---|
| Paper | `oklch(94.4% 0.0144 84.6)` | Side columns and page |
| Ink | `oklch(21.4% 0.0119 167.3)` | The stage and all text on paper |
| On air | `oklch(66.6% 0.2237 34.3)` | Recording and the one primary action. A fill with Ink text, or a light on the stage. Never text on paper |
| Phosphor | `oklch(88.1% 0.1237 167.9)` | The microphone's halo, rim light and analysis slats only |

Every other tone is Ink at reduced opacity on Paper, or Paper on Ink. Secondary text is at least `ink/70`, which passes AA. Status uses shape and words: a filled dot for ready or done, a hollow dot for anything else. Light theme only.

## Type

- **Gentium Book Plus** (`font-display`): titles, every phonetic symbol, prompts and the model text. It has full IPA coverage.
- **Schibsted Grotesk** (`font-sans`): the interface. Use `.num` (tabular figures) only on runs of digits, because the face's tabular colon and period set wide.
- Body is 17 px, labels 13 px. The Title's display size is `clamp(4rem, 6.5vw, 7.5rem)`.
- A phonetic pair reads as the target, then the error: "/θ/ not /t/" (`shared/ui/PhoneticPair.tsx`).

Both fonts are self-hosted through `@fontsource`; nothing loads from a CDN.

## The microphone

- `shared/audio/MicStage.tsx` holds the real `<button>` (`aria-pressed`, Space as the shortcut, an `aria-live` state), the CSS radial halo, the time arc and a flat SVG silhouette.
- `MicScene.tsx` is the lazy-loaded three.js model. It is built from geometry, with an eleven-slat capsule head, a short neck, a U-shaped yoke and a round base. It uses metal PBR materials, a `RoomEnvironment` map, a top-left key light, a Phosphor rim light and a contact shadow.
- Rendering is on demand, with the pixel ratio capped at 2. Frames run only while something moves or the microphone is on air.
- The level reaches the halo through one CSS custom property, written per frame. No React state changes per frame.
- States:
  - idle: dim glow;
  - ready: the lamp lights;
  - recording: the lamp turns On air, the halo follows the voice, and the arc fills over the time limit;
  - analyzing: the slats light from bottom to top with the job's real progress;
  - done: everything settles to idle;
  - error: the glow is off and the message shows in the right Text slot.
- Without WebGL, the silhouette stays and recording still works. Shared measurements live in `micGeometry.ts`.

## Motion

- Easing is `--ease-out` `cubic-bezier(0.23, 1, 0.32, 1)`. Pressing a control scales it to 0.97 over 140 ms.
- On a state change, each slot's new content fades up 8 px over 220 ms, with a 35 ms stagger, and the old content leaves at once. The entrance plays once per page load, not on navigation.
- The silhouette hands over to the 3D scene with a 240 ms cross-fade. The halo eases over 220 ms, except while recording, when it follows the voice directly. Hover effects are gated to fine pointers.
- Under reduced motion, slots only fade, presses do not scale, the halo steps in quarters, and the pointer tilt is off.

## Not allowed

- No glow other than the microphone's.
- No gradients on text or backgrounds, glass, neon outlines, emoji icons or nested cards.
- No bounce or elastic easing, and no decorative spinners.
- No marketing copy or invented numbers: every value on screen comes from the API.
