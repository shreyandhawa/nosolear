# Design

The Nosolear app is one dark studio in the Ice palette: a single near-black ground with a faint grid, light text, square corners, and one glowing 3D microphone at the centre, which is the record control. It should read like a well-made dictionary and a recording booth, never a dashboard. Product truth lives in PRODUCT.md.

## Layout

One layout for every screen (`shared/ui/Desk.tsx`), under a 60 px navigation bar. The page is twelve square cells wide and the columns take 4 / 5 / 3 of them (`minmax(0, fr)`, so long tokens never widen the page). The left column holds Title (the top half), then Media and Text at 75% of its width (full width when the slot holds a table). The centre is the stage with the microphone, full height, on the same ground as the columns, so nothing but the microphone's light sets it apart. The right column holds Card and Text, which share the height, and a short CTA bar. No hairlines divide the columns or the slots: the grid is the structure. States swap content, never layout, and the microphone never moves. Designed at 1440 by 900, holds from 1280 to 1728, and degrades without breaking at 1024. There is no phone layout yet.

The grid is drawn on `.desk` in CSS: lines at 5% of the text colour on cells of `100vw / 12`, and a 10 px plus mark at 34% where they cross. It fades out round the microphone, because the 3D canvas covers it.

Corners are square everywhere; only status dots and the microphone are round. The Card slot is the one bordered element (`.chamfer`): a 1 px accent line with the bottom-right corner cut at 45 degrees (28 px), and more padding below so the cut never touches the last line.

## Colour

Tokens are in `index.css` `@theme`, as hex, because `MicScene.tsx` repeats them as three.js constants and the two must match exactly. One background everywhere: Ink is the ground (`--color-bg`) and Paper the text (`--color-fg`); pages use the `bg` and `fg` roles, never the raw names.

| Token | Value | Use |
|---|---|---|
| Ink (`bg`) | `#07090B` | The ground of every screen, and the text on Accent and On air |
| Paper (`fg`) | `#F2F5F7` | All text, the grid, hairlines (`fg/12`), selected states |
| Accent | `#AFDDFF` | The one primary action (a fill with Ink text) and the card's outline |
| On air | `#FF5B4A` | Recording only: the pressed action, the lamp, the time arc and the On air badge |
| Glow | `#AFDDFF` | The microphone's glow, rim light and lit slats only |

Secondary text is `fg/72` (about 9:1 on Ink). Light text on the dark ground gets a touch more leading (1.6) and tracking (0.005em). Status is shape plus words: a filled dot for ready or done, a hollow dot otherwise. The 3D canvas renders without tone mapping, so its background is the page's Ink. Bloom still lifts it a touch, so the canvas fades out at its edges (a radial mask) and the stage has no edge.

## Type

- **Gentium Book Plus** (`font-display`): titles, every phonetic symbol, prompts and the model text. It has full IPA coverage.
- **Schibsted Grotesk** (`font-sans`): the interface. Use `.num` (tabular figures) only on runs of digits, because the face's tabular colon and period set wide.
- Body is 17 px, labels 13 px. The Title's display size is `clamp(4rem, 6.5vw, 7.5rem)`.
- A phonetic pair reads as the target, then the error: "/θ/ not /t/" (`shared/ui/PhoneticPair.tsx`).

Both fonts are self-hosted through `@fontsource`; nothing loads from a CDN.

## The microphone

`shared/audio/MicStage.tsx` holds the real `<button>` (`aria-pressed`, Space, an `aria-live` state), the time arc, a flat SVG silhouette (shown while loading and without WebGL, with a CSS halo), and the pointer drag. `MicScene.tsx` is the lazy-loaded three.js model, built from geometry: an eleven-slat capsule head with two front ribs (so every turn reads), a short neck, a U-shaped yoke and a round base. Metal PBR materials, a `RoomEnvironment` map, a top-left key light, a Glow rim light, a contact shadow, and real bloom (`EffectComposer`, `UnrealBloomPass` at threshold 1, `OutputPass`) on an opaque Ink canvas 1.8 times the overlay box, so the glow has room. An additive Glow sprite behind the head is the glow and the level meter: its size and opacity, the rim and the bloom strength follow the voice per frame, read from a ref with no React state per frame.

Motion: a three-quarter resting pose; an idle float (±7° turn over 4 s, a small bob over 3 s); a turn toward the pointer anywhere in the window (±25° across, ±10° up and down); drag to rotate (past 4 px it is a drag, not a press; it eases back on release, the short way round); and a lean into the voice while recording. States: idle (dim glow), ready (the lamp lights), recording (the lamp turns On air, the slats and glow pulse with the voice, the arc fills over the time limit), analyzing (the slats light bottom to top with the job's real progress), done (settles), error (glow off, the message in the right Text slot). Without WebGL the silhouette stays, a warning is logged, and recording still works. Shared measurements live in `micGeometry.ts`.

## Motion

`--ease-out` `cubic-bezier(0.23, 1, 0.32, 1)`; presses scale to 0.97 over 140 ms. On a state change each slot's new content fades up 8 px over 220 ms with a 35 ms stagger, and the old content leaves at once; the entrance plays once per page load, not on navigation. The silhouette hands over to the 3D scene with a 240 ms cross-fade. The microphone's motion is one requestAnimationFrame loop with exponential easing toward its targets (interruptible); it runs while the tab is visible. Under reduced motion the loop renders only on change: no float, no pointer turn, drag snaps back, slots only fade, presses do not scale, and the glow steps in quarters.

## Not allowed

- No glow other than the microphone's, and no second background colour.
- No rounded corners, no second bordered card, and no hairlines between columns.
- No gradients on text or backgrounds, glass, neon outlines, emoji icons or nested cards.
- No bounce or elastic easing, and no decorative spinners.
- No marketing copy or invented numbers: every value on screen comes from the API.
