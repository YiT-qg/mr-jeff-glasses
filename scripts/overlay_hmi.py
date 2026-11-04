"""Burn a synthetic HMI error panel into a clip, labeled SIMULATED.

Usage: .venv/bin/python scripts/overlay_hmi.py in.mp4 out.mp4 [--frames 0-14]
       [--code E-204] [--title "Spindle overtemp"] [--asset CNC-07]
"""
from __future__ import annotations
import argparse

import cv2
import imageio.v2 as imageio
import numpy as np


def burn_hmi(bgr: np.ndarray, code: str, title: str, asset: str) -> np.ndarray:
    h, w = bgr.shape[:2]
    x0, y0, x1, y1 = int(w * 0.12), int(h * 0.32), int(w * 0.88), int(h * 0.62)
    cv2.rectangle(bgr, (x0, y0), (x1, y1), (18, 18, 22), -1)
    cv2.rectangle(bgr, (x0, y0), (x1, y0 + 64), (30, 30, 220), -1)
    cv2.putText(bgr, "FAULT", (x0 + 16, y0 + 44), cv2.FONT_HERSHEY_SIMPLEX,
                1.1, (255, 255, 255), 2)
    cv2.putText(bgr, code, (x0 + 16, y0 + 130), cv2.FONT_HERSHEY_SIMPLEX,
                1.6, (255, 255, 255), 3)
    cv2.putText(bgr, title[:22], (x0 + 16, y0 + 175), cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (255, 255, 255), 2)
    cv2.putText(bgr, asset, (x0 + 16, y1 - 52), cv2.FONT_HERSHEY_SIMPLEX,
                0.9, (200, 200, 200), 2)
    cv2.putText(bgr, "SIMULATED HMI", (x0 + 16, y1 - 18), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (150, 150, 150), 2)
    cv2.rectangle(bgr, (x0, y0), (x1, y1), (120, 120, 130), 2)
    return bgr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--frames", default="0-14")
    ap.add_argument("--code", default="E-204")
    ap.add_argument("--title", default="Spindle overtemp")
    ap.add_argument("--asset", default="CNC-07")
    args = ap.parse_args()
    start, end = (int(x) for x in args.frames.split("-"))

    reader = imageio.get_reader(args.input, "ffmpeg")
    meta = reader.get_meta_data()
    writer = imageio.get_writer(args.output, fps=meta.get("fps", 5),
                                codec="libx264", quality=8, macro_block_size=None)
    n = 0
    for rgb in reader:
        bgr = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)
        if start <= n <= end:
            bgr = burn_hmi(bgr, args.code, args.title, args.asset)
        writer.append_data(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        n += 1
    reader.close()
    writer.close()
    print(f"wrote {args.output}: {n} frames, HMI {args.code} on {start}-{end}")


if __name__ == "__main__":
    main()
