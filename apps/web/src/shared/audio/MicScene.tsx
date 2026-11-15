import { useEffect, useRef, type RefObject } from "react";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { HEAD, SLATS, VIEW } from "./micGeometry";
import type { MicState } from "./MicStage";

const PHOSPHOR = 0x7cf2c8;
const ON_AIR = 0xff4a1c;
const PAPER = 0xf1ece2;

type Props = {
  state: MicState;
  progress: number;
  level: RefObject<number>;
  reduced: boolean;
  onReady: () => void;
  onFail: () => void;
};

type Live = { set: (state: MicState, progress: number, reduced: boolean) => void };

/** The 3D microphone, built from three.js geometry. Decorative: the button sits over it.
 * Renders on demand; frames run only while something moves or the microphone is on air. */
export default function MicScene({ state, progress, level, reduced, onReady, onFail }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const live = useRef<Live | null>(null);
  const callbacks = useRef({ onReady, onFail });

  useEffect(() => {
    const el = canvas.current!;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas: el, alpha: true, antialias: true });
    } catch {
      callbacks.current.onFail();
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.setClearColor(0x000000, 0);

    const scene = new THREE.Scene();
    const pmrem = new THREE.PMREMGenerator(renderer);
    const room = new RoomEnvironment();
    scene.environment = pmrem.fromScene(room, 0.04).texture;
    scene.environmentIntensity = 0.55;
    room.dispose();

    const fov = 22;
    const camera = new THREE.PerspectiveCamera(fov, VIEW.w / VIEW.h, 0.1, 50);
    const distance = VIEW.h / 2 / Math.tan(THREE.MathUtils.degToRad(fov / 2));
    camera.position.set(0, VIEW.cy + 0.55, distance);
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
      return mesh;
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
    // Neck, lamp, yoke with its pivots, stem and a round base.
    add(new THREE.CylinderGeometry(0.16, 0.2, 0.27, 40), body, (m) => m.position.setY(1.485));
    add(new THREE.SphereGeometry(0.045, 20, 12), lampMat, (m) => m.position.set(0, 1.47, 0.19));
    add(new THREE.TorusGeometry(0.8, 0.055, 16, 72, Math.PI), body, (m) => {
      m.rotation.z = Math.PI;
      m.position.setY(2.15);
    });
    for (const side of [-1, 1]) {
      add(new THREE.CylinderGeometry(0.055, 0.055, 0.45, 20), body, (m) => m.position.set(side * 0.8, 2.375, 0));
      add(new THREE.CylinderGeometry(0.075, 0.075, 0.26, 24), bright, (m) => {
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

    // A soft contact shadow under the base.
    const shadowCanvas = document.createElement("canvas");
    shadowCanvas.width = shadowCanvas.height = 128;
    const g = shadowCanvas.getContext("2d")!;
    const gradient = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    gradient.addColorStop(0, "rgba(0,0,0,0.75)");
    gradient.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = gradient;
    g.fillRect(0, 0, 128, 128);
    const shadowTexture = new THREE.CanvasTexture(shadowCanvas);
    const shadow = new THREE.Mesh(
      new THREE.PlaneGeometry(2.8, 1.2),
      new THREE.MeshBasicMaterial({ map: shadowTexture, transparent: true, depthWrite: false }),
    );
    shadow.rotation.x = -Math.PI / 2;
    shadow.position.y = 0.002;
    scene.add(shadow);

    // State the frames read.
    let current: MicState = "idle";
    let target = 0;
    let glow = 0;
    let still = false;
    const tilt = { x: 0, y: 0, tx: 0, ty: 0 };
    let frame = 0;
    const invalidate = () => {
      if (!frame) frame = requestAnimationFrame(render);
    };

    function render() {
      frame = 0;
      const ease = still ? 1 : 0.12;
      tilt.x += (tilt.tx - tilt.x) * ease;
      tilt.y += (tilt.ty - tilt.y) * ease;
      glow += (target - glow) * (still ? 1 : 0.15);
      mic.rotation.set(tilt.x, tilt.y, 0);
      slats.forEach((m, i) => {
        m.emissiveIntensity = THREE.MathUtils.clamp(glow * slats.length - i, 0, 1) * 1.4;
      });
      const voice = current === "recording" ? (level.current ?? 0) : 0;
      rim.intensity = current === "error" ? 0 : 0.8 + voice * 5;
      lampMat.emissive.setHex(current === "recording" ? ON_AIR : PAPER);
      lampMat.emissiveIntensity = current === "recording" ? 3 : current === "ready" ? 1.2 : 0;
      renderer.render(scene, camera);
      const moving =
        Math.abs(tilt.tx - tilt.x) + Math.abs(tilt.ty - tilt.y) > 0.0005 || Math.abs(target - glow) > 0.002;
      if (moving || current === "recording") invalidate();
    }

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = el;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      invalidate();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(el);

    // A few degrees toward the pointer, eased. No orbit, no zoom.
    const stage = el.closest(".stage") ?? el;
    const onMove = (e: Event) => {
      if (still) return;
      const p = e as PointerEvent;
      const r = stage.getBoundingClientRect();
      tilt.ty = ((p.clientX - r.left) / r.width - 0.5) * 0.22;
      tilt.tx = ((p.clientY - r.top) / r.height - 0.5) * 0.08;
      invalidate();
    };
    const onLeave = () => {
      tilt.tx = tilt.ty = 0;
      invalidate();
    };
    stage.addEventListener("pointermove", onMove);
    stage.addEventListener("pointerleave", onLeave);

    live.current = {
      set(state, progress, reduced) {
        current = state;
        still = reduced;
        if (reduced) tilt.tx = tilt.ty = 0;
        target = state === "analyzing" ? progress : 0;
        invalidate();
      },
    };
    resize();
    callbacks.current.onReady();

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      stage.removeEventListener("pointermove", onMove);
      stage.removeEventListener("pointerleave", onLeave);
      scene.traverse((o) => {
        if (o instanceof THREE.Mesh) {
          o.geometry.dispose();
          (o.material as THREE.Material).dispose();
        }
      });
      shadowTexture.dispose();
      scene.environment?.dispose();
      pmrem.dispose();
      renderer.dispose();
      live.current = null;
    };
  }, [level]);

  useEffect(() => live.current?.set(state, progress, reduced), [state, progress, reduced]);

  return <canvas ref={canvas} aria-hidden className="mic-scene absolute inset-0 size-full" />;
}
