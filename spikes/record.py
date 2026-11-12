"""Record the spike sets from the mic: uv run python record.py {calibration|read_aloud|free_talk} [--list]."""
import argparse
import sys
import threading
import time

import numpy as np
import soundfile as sf

from common import DATA, TARGET_RATE, write_wav16k
from items import CALIBRATION, FREE_TALK_PROMPT, READ_ALOUD

FREE_TALK_SECONDS = 60
MIN_PEAK_DBFS = -50.0


def build_items(which: str) -> list[tuple[str, str]]:
    if which == "calibration":
        return [(c.id, c.instruction) for c in CALIBRATION]
    if which == "read_aloud":
        return [(f"ra{i}", f'Read aloud: "{s}"') for i, s in enumerate(READ_ALOUD, 1)]
    return [("free_talk", f"Free talk, {FREE_TALK_SECONDS} s: {FREE_TALK_PROMPT}")]


def capture(rate: int, fixed_seconds: int | None) -> np.ndarray:
    import sounddevice as sd

    chunks: list[np.ndarray] = []
    stop = threading.Event()
    stream = sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                            callback=lambda indata, f, t, s: chunks.append(indata[:, 0].copy()))
    with stream:
        if fixed_seconds:
            for left in range(fixed_seconds, 0, -1):
                print(f"\r  recording... {left:2d}s left ", end="", flush=True)
                time.sleep(1)
            print()
        else:
            threading.Thread(target=lambda: (input("  recording... press Enter to stop "), stop.set()),
                             daemon=True).start()
            stop.wait()
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)


def peak_dbfs(x: np.ndarray) -> float:
    p = float(np.max(np.abs(x))) if len(x) else 0.0
    return 20 * np.log10(p) if p > 0 else -120.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("set", choices=["calibration", "read_aloud", "free_talk"])
    ap.add_argument("--list", action="store_true", help="print ids and instructions; no mic")
    args = ap.parse_args()
    items = build_items(args.set)
    if args.list:
        for i, ins in items:
            print(f"{i}\t{ins}")
        print(f"{len(items)} items")
        return 0

    import sounddevice as sd

    dev = sd.query_devices(kind="input")
    rate = int(dev["default_samplerate"])
    print(f"Input device: {dev['name']}  (native rate {rate} Hz)")
    out_dir = DATA / "rec" / args.set
    for n, (item_id, instruction) in enumerate(items, 1):
        path = out_dir / f"{item_id}.wav"
        if path.exists():
            continue
        while True:
            print(f"\n[{n}/{len(items)}] {item_id}\n  {instruction}")
            input("  Press Enter to start ")
            audio = capture(rate, FREE_TALK_SECONDS if args.set == "free_talk" else None)
            peak = peak_dbfs(audio)
            print(f"  duration {len(audio) / rate:.2f}s, peak {peak:.1f} dBFS")
            if peak < MIN_PEAK_DBFS:
                print("  Take rejected: almost silent. macOS may be blocking the microphone "
                      "(System Settings -> Privacy & Security -> Microphone).")
                choice = input("  [Enter]=retry  q=quit ").strip().lower()
                if choice == "q":
                    return 0
                continue
            choice = input("  [Enter]=keep  r=redo  q=quit ").strip().lower()
            if choice == "q":
                return 0
            if choice == "r":
                continue
            write_wav16k(path, audio, rate)
            info = sf.info(str(path))
            assert (info.samplerate, info.channels) == (TARGET_RATE, 1), f"bad format: {path}"
            break
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
