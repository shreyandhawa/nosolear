// Shared measurements (model units) so the 3D scene, the flat silhouette, the arc and the button
// all line up. The view is 4.3 units tall and 3.225 wide, centred at y 1.95.
export const VIEW = { cx: 0, cy: 1.95, h: 4.3, w: 3.225 };
export const HEAD = { y: 2.75, r: 0.6, half: 1.15 };
export const ARC_R = 1.3;
/** The 3D canvas is this many times the overlay box, around the same centre, so the glow and
 * bloom have room and the overlays still line up. */
export const CANVAS_SCALE = 1.8;
export const SLATS = Array.from({ length: 11 }, (_, i) => {
  const y = 1.78 + (i * (3.72 - 1.78)) / 10;
  const beyond = Math.max(0, Math.abs(y - HEAD.y) - (HEAD.half - HEAD.r));
  return { y, r: Math.sqrt(Math.max(0, HEAD.r ** 2 - beyond ** 2)) };
});
/** Model y to SVG y within the view box. */
export const svgY = (y: number) => -y;
export const VIEW_BOX = `${-VIEW.w / 2} ${-(VIEW.cy + VIEW.h / 2)} ${VIEW.w} ${VIEW.h}`;
