import { useEffect, useRef, type RefObject } from "react";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { CANVAS_SCALE, HEAD, SLATS, VIEW } from "./micGeometry";
import type { MicState } from "./MicStage";

const INK = 0x141b18;
const PHOSPHOR = 0x7cf2c8;
const ON_AIR = 0xff4a1c;
const PAPER = 0xf1ece2;
const POSE = { x: 0.06, y: -0.35 }; // a three-quarter turn, so it reads as an object
const TAU = Math.PI * 2;

/** Written by MicStage's pointer handlers; the scene sets `wake` so a drag renders frames even
 * when the loop is idle (reduced motion). */
export type Drag = { active: boolean; x: number; y: number; wake?: () => void };

type Props = {
  state: MicState;
  progress: number;
  level: RefObject<number>;
  drag: RefObject<Drag>;
  reduced: boolean;
  onReady: () => void;
  onFail: () => void;
};

type Live = { set: (state: MicState, progress: number, reduced: boolean) => void; wake: () => void };

/** A soft radial texture, drawn in code (no image file). */
function radial(stops: [number, string][]) {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d")!;
  const gradient = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  for (const [at, colour] of stops) gradient.addColorStop(at, colour);
  g.fillStyle = gradient;
  g.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
}

/** The 3D microphone: built from three.js geometry, lit by a room environment, a key light and a
 * Phosphor rim, with real bloom. It floats, turns toward the pointer, turns when dragged and leans
 * into the voice. Decorative: the button sits over it. */
export default function MicScene({ state, progress, level, drag, reduced, onReady, onFail }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const live = useRef<Live | null>(null);
  const callbacks = useRef({ onReady, onFail });

  useEffect(() => {
    const el = canvas.current!;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas: el, antialias: true });
    } catch (err) {
      console.warn("mic scene unavailable", (err as Error).name);
      callbacks.current.onFail();
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.toneMapping = THREE.NoToneMapping;
    const ground = new THREE.Color(INK);
    renderer.setClearColor(ground, 1);

    const scene = new THREE.Scene();
    scene.background = ground;
    const pmrem = new THREE.PMREMGenerator(renderer);
    const room = new RoomEnvironment();
    scene.environment = pmrem.fromScene(room, 0.04).texture;
    scene.environmentIntensity = 0.55;
    room.dispose();

    // The canvas is CANVAS_SCALE times the overlay box, around the same centre, so the overlays
    // (arc, button, silhouette) still line up and the glow has room.
    const fov = 22;
    const camera = new THREE.PerspectiveCamera(fov, VIEW.w / VIEW.h, 0.1, 80);
    const distance = (VIEW.h * CANVAS_SCALE) / 2 / Math.tan(THREE.MathUtils.degToRad(fov / 2));
    camera.position.set(0, VIEW.cy + 0.9, distance);
    camera.lookAt(0, VIEW.cy, 0);

    const key = new THREE.DirectionalLight(0xfff6ea, 2.4);
    key.position.set(-3, 5, 4);
    const rim = new THREE.DirectionalLight(PHOSPHOR, 0.8);
    rim.position.set(0.6, 3.2, -4);
    scene.add(key, rim);

    const body = new THREE.MeshPhysicalMaterial({ color: 0x2c3230, metalness: 1, roughness: 0.42, anisotropy: 0.6 });
    const bright = new THREE.MeshStandardMaterial({ color: 0xd9dad4, metalness: 1, roughness: 0.22 });
    const core = new THREE.MeshStandardMaterial({ color: 0x0b0e0d, metalness: 0.3, roughness: 0.85 });
    const lampMat = new THREE.MeshStandardMaterial({ color: 0x111111, emissive: PAPER, emissiveIntensity: 0 });

    const mic = new THREE.Group();
    const add = (geometry: THREE.BufferGeometry, material: THREE.Material, place: (m: THREE.Mesh) => void) => {
      const mesh = new THREE.Mesh(geometry, material);
      place(mesh);
      mic.add(mesh);
    };
    // Head: a dark core with eleven bright slats around it.
    add(new THREE.CapsuleGeometry(HEAD.r - 0.04, (HEAD.half - HEAD.r) * 2, 12, 48), core, (m) => m.position.setY(HEAD.y));
    const slats = SLATS.map((s) => {
      const material = bright.clone();
      material.emissive = new THREE.Color(PHOSPHOR);
      material.emissiveIntensity = 0;
      add(new THREE.TorusGeometry(s.r + 0.01, 0.03, 12, 72), material, (m) => {
        m.rotation.x = Math.PI / 2;
        m.position.setY(s.y);
      });
      return material;
    });
    // Two ribs down the front of the grille give the head a front, so every turn reads.
    for (const angle of [-0.55, 0.55]) {
      const path = new THREE.CatmullRomCurve3(
        SLATS.map((s) => new THREE.Vector3(Math.sin(angle) * (s.r + 0.035), s.y, Math.cos(angle) * (s.r + 0.035))),
      );
      add(new THREE.TubeGeometry(path, 48, 0.026, 10), bright, () => {});
    }
    // Neck, lamp, yoke with its pivots, stem and a round base.
    add(new THREE.CylinderGeometry(0.16, 0.2, 0.27, 40), body, (m) => m.position.setY(1.485));
    add(new THREE.SphereGeometry(0.045, 20, 12), lampMat, (m) => m.position.set(0, 1.47, 0.19));
    add(new THREE.TorusGeometry(0.8, 0.055, 16, 72, Math.PI), body, (m) => {
      m.rotation.z = Math.PI;
      m.position.setY(2.15);
    });
    for (const side of [-1, 1]) {
      add(new THREE.CylinderGeometry(0.055, 0.055, 0.45, 20), body, (m) => m.position.set(side * 0.8, 2.375, 0));
      add(new THREE.CylinderGeometry(0.075, 0.075, 0.26, 24), body, (m) => {
        m.rotation.z = Math.PI / 2;
        m.position.set(side * 0.72, 2.6, 0);
      });
      add(new THREE.CylinderGeometry(0.11, 0.11, 0.07, 32), body, (m) => {
        m.rotation.z = Math.PI / 2;
        m.position.set(side * 0.88, 2.6, 0);
      });
    }
    add(new THREE.CylinderGeometry(0.06, 0.06, 1.19, 20), body, (m) => m.position.setY(0.755));
    const profile = [
      [0, 0],
      [0.9, 0],
      [0.93, 0.03],
      [0.91, 0.12],
      [0.8, 0.16],
      [0, 0.16],
    ].map(([x, y]) => new THREE.Vector2(x, y));
    add(new THREE.LatheGeometry(profile, 72), body, () => {});
    scene.add(mic);

    // The glow: an additive Phosphor sprite behind the head, bright enough to bloom. It is the
    // level meter while recording.
    const glowTexture = radial([
      [0, "rgba(255,255,255,1)"],
      [0.35, "rgba(255,255,255,0.35)"],
      [1, "rgba(255,255,255,0)"],
    ]);
    const glowMat = new THREE.SpriteMaterial({
      map: glowTexture,
      color: new THREE.Color(PHOSPHOR).multiplyScalar(1.4),
      blending: THREE.AdditiveBlending,
      transparent: true,
      depthWrite: false,
    });
    const glow = new THREE.Sprite(glowMat);
    glow.position.set(0, HEAD.y, -0.9);
    scene.add(glow);

    // A soft contact shadow under the base.
    const shadowTexture = radial([
      [0, "rgba(0,0,0,0.8)"],
      [1, "rgba(0,0,0,0)"],
    ]);
    const shadow = new THREE.Mesh(
      new THREE.PlaneGeometry(2.8, 1.2),
      new THREE.MeshBasicMaterial({ map: shadowTexture, transparent: true, depthWrite: false }),
    );
    shadow.rotation.x = -Math.PI / 2;
    shadow.position.y = 0.002;
    scene.add(shadow);

    // Bloom: emissive slats, the lamp, the glow and hot highlights bleed light.
    const composer = new EffectComposer(
      renderer,
      new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: 4 }),
    );
    composer.addPass(new RenderPass(scene, camera));
    const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.55, 0.45, 1);
    composer.addPass(bloom);
    composer.addPass(new OutputPass());

    // State the frames read.
    let current: MicState = "idle";
    let still = false;
    let target = 0;
    let lit = 0;
    let wasDragging = false;
    const turn = { x: POSE.x, y: POSE.y };
    const follow = { x: 0, y: 0 };
    let frame = 0;
    const invalidate = () => {
      if (!frame) frame = requestAnimationFrame(render);
    };

    function render(now: number) {
      frame = 0;
      const d = drag.current ?? { active: false, x: 0, y: 0 };
      const voice = current === "recording" ? (level.current ?? 0) : 0;
      // Released: unwind whole turns so the ease back takes the short way round.
      if (wasDragging && !d.active) turn.y = POSE.y + Math.atan2(Math.sin(turn.y - POSE.y), Math.cos(turn.y - POSE.y));
      wasDragging = d.active;
      const float = still ? 0 : 0.12 * Math.sin((now / 4000) * TAU);
      const ty = d.active ? POSE.y + d.y : POSE.y + float + (still ? 0 : follow.y);
      const tx = THREE.MathUtils.clamp(
        (d.active ? POSE.x + d.x : POSE.x + (still ? 0 : follow.x)) + voice * 0.12,
        -0.44,
        0.44,
      );
      const ease = d.active ? 0.35 : still ? 1 : 0.08;
      turn.y += (ty - turn.y) * ease;
      turn.x += (tx - turn.x) * ease;
      mic.rotation.set(turn.x, turn.y, 0);
      mic.position.y = still ? 0 : 0.03 * Math.sin((now / 3000) * TAU);

      lit += (target - lit) * (still ? 1 : 0.15);
      slats.forEach((m, i) => {
        m.emissiveIntensity = THREE.MathUtils.clamp(lit * slats.length - i, 0, 1) * 1.6 + voice * 0.8;
      });
      const base = current === "error" ? 0 : current === "ready" ? 0.22 : current === "recording" ? 0.2 : 0.16;
      glowMat.opacity = base + voice * 0.7;
      glow.scale.setScalar(3 + voice * 1.6);
      rim.intensity = current === "error" ? 0 : 0.8 + voice * 5;
      bloom.strength = 0.55 + voice * 0.9;
      lampMat.emissive.setHex(current === "recording" ? ON_AIR : PAPER);
      lampMat.emissiveIntensity = current === "recording" ? 4 : current === "ready" ? 1.6 : 0;
      composer.render();

      const settling =
        Math.abs(ty - turn.y) + Math.abs(tx - turn.x) > 0.0005 || Math.abs(target - lit) > 0.002;
      if (!still || d.active || settling || current === "recording") invalidate();
    }

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = el;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      composer.setPixelRatio(Math.min(devicePixelRatio, 2));
      composer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      invalidate();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(el);

    // Turns toward the pointer anywhere in the window: up to 25° across, 10° up and down.
    const onMove = (e: PointerEvent) => {
      follow.y = (e.clientX / innerWidth - 0.5) * 0.87;
      follow.x = (e.clientY / innerHeight - 0.5) * 0.35;
      if (still) return;
      invalidate();
    };
    window.addEventListener("pointermove", onMove);

    live.current = {
      set(state, progress, reduced) {
        current = state;
        still = reduced;
        target = state === "analyzing" ? progress : 0;
        invalidate();
      },
      wake: invalidate,
    };
    drag.current.wake = invalidate;
    resize();
    callbacks.current.onReady();

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("pointermove", onMove);
      scene.traverse((o) => {
        if (o instanceof THREE.Mesh || o instanceof THREE.Sprite) {
          o.geometry.dispose();
          (o.material as THREE.Material).dispose();
        }
      });
      glowTexture.dispose();
      shadowTexture.dispose();
      scene.environment?.dispose();
      pmrem.dispose();
      bloom.dispose();
      composer.dispose();
      renderer.dispose();
      live.current = null;
    };
  }, [level, drag]);

  useEffect(() => live.current?.set(state, progress, reduced), [state, progress, reduced]);

  return <canvas ref={canvas} aria-hidden className="mic-scene size-full" />;
}
