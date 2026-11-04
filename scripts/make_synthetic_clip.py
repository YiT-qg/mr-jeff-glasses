"""Generate a synthetic dwell-test clip (SIMULATED scenes, no licensed footage).

12 s @ 5 fps: static WORKSHOP -> motion -> static HMI E-204 -> motion.
Expect exactly 2 dwell events with default settings (2.5 s stillness).
"""
import sys
from pathlib import Path

import cv2
import imageio.v2 as imageio
import numpy as np

W, H, FPS = 504, 896, 5


def scene(bg: tuple[int, int, int], panel, texts) -> np.ndarray:
    img = np.full((H, W, 3), bg, np.uint8)
    x0, y0, x1, y1, color = panel
    cv2.rectangle(img, (x0, y0), (x1, y1), color, -1)
    y = 120
    for text, scale, color in texts:
        cv2.putText(img, text, (40, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2)
        y += 60
    cv2.putText(img, "SIMULATED", (40, H - 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (150, 150, 150), 2)
    return img


def motion(base: np.ndarray, rng, n: int) -> list:
    # Alternating full/dark frames: survives x264 smoothing, unlike noise,
    # so the dwell detector always sees motion here and re-arms.
    dark = (base * 0.25).astype(np.uint8)
    return [base if i % 2 == 0 else dark for i in range(n)]


def write(path: str, frames: list) -> None:
    out = imageio.get_writer(path, fps=FPS, codec="libx264", quality=8, macro_block_size=None)
    for f in frames:
        out.append_data(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
    out.close()
    print(f"wrote {path}: {len(frames)} frames @ {FPS}fps ({len(frames)/FPS:.1f}s)")


def main(path: str) -> None:
    workshop = scene((60, 60, 66), (120, 380, 384, 620, (90, 90, 100)),
                     [("CNC-07", 1.2, (255, 255, 255)), ("WORKSHOP", 0.9, (200, 200, 200))])
    hmi = scene((20, 20, 24), (100, 300, 404, 520, (40, 40, 200)),
                [("E-204", 1.4, (255, 255, 255)), ("Spindle overtemp", 0.8, (255, 255, 255))])
    rng = np.random.default_rng(7)
    write(path, [workshop] * 15 + motion(workshop, rng, 10) + [hmi] * 20 + motion(hmi, rng, 10))


def cnc07_base(path: str) -> None:
    """Base for the RCA demo: HMI machine + photorealistic check spots.

    overlay_hmi.py then burns the E-204 panel onto frames 0-14."""
    from pathlib import Path as _P
    stills = _P(__file__).resolve().parent.parent / "data" / "stills"

    def still(name: str) -> np.ndarray:
        img = cv2.imread(str(stills / name))
        if img is None:
            raise FileNotFoundError(f"missing still: {stills / name}")
        return cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)

    machine = scene((48, 48, 54), (110, 400, 394, 640, (80, 80, 92)),
                    [("BAY 2", 1.0, (220, 220, 220))])
    filt = still("filter.jpg")
    reservoir = still("reservoir.jpg")
    spindle = still("spindle.jpg")
    rng = np.random.default_rng(11)
    write(path, [machine] * 15 + motion(machine, rng, 8) + [filt] * 15 +
          motion(filt, rng, 8) + [reservoir] * 15 + motion(reservoir, rng, 8) +
          [spindle] * 15 + motion(spindle, rng, 8))


def still_clip(still_path: str, path: str) -> None:
    """One-dwell clip from a single still (retail/wandering demos)."""
    img = cv2.imread(still_path)
    if img is None:
        raise FileNotFoundError(still_path)
    img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
    rng = np.random.default_rng(3)
    write(path, [img] * 15 + motion(img, rng, 8))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cnc07-base":
        cnc07_base(sys.argv[2] if len(sys.argv) > 2 else "data/clips/cnc07_base.mp4")
    elif len(sys.argv) > 3 and sys.argv[1] == "--still-clip":
        still_clip(sys.argv[2], sys.argv[3])
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else "data/clips/synth_dwell_test.mp4")
