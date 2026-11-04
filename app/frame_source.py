"""Frame sources. Everything downstream sees 504x896 RGB @ 5 fps.

This is the seam where a real glasses stream (phone app pushing frames)
replaces the video-file/webcam stand-ins without touching dwell/router code.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

WIDTH, HEIGHT, FPS = 504, 896, 5


@dataclass
class Frame:
    idx: int
    t: float  # seconds on the source timeline
    image: Image.Image  # RGB, 504x896


def _to_frame(idx: int, t: float, bgr: np.ndarray) -> Frame:
    small = cv2.resize(bgr, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    return Frame(idx=idx, t=t, image=Image.fromarray(rgb))


class VideoFileSource:
    """Reads a video file (imageio-ffmpeg backend), emitting frames resampled to 5 fps."""

    def __init__(self, path: str | Path):
        import imageio.v2 as imageio

        self.path = str(path)
        if not Path(self.path).exists():
            raise FileNotFoundError(f"cannot open video: {self.path}")
        with imageio.get_reader(self.path, "ffmpeg") as r:
            meta = r.get_meta_data()
        native = float(meta.get("fps") or FPS)
        self.interval = max(1, round(native / FPS))
        self.native_fps = native

    def __iter__(self):
        import imageio.v2 as imageio

        idx = raw = 0
        with imageio.get_reader(self.path, "ffmpeg") as r:
            for rgb in r:
                if raw % self.interval == 0:
                    bgr = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)
                    yield _to_frame(idx, raw / self.native_fps, bgr)
                    idx += 1
                raw += 1


class WebcamSource:
    """Laptop/phone webcam, paced to 5 fps. Ctrl-C or max_frames to stop."""

    def __init__(self, device: int = 0, max_frames: int | None = None):
        self.device = device
        self.max_frames = max_frames

    def __iter__(self):
        import time

        cap = cv2.VideoCapture(self.device)
        if not cap.isOpened():
            raise RuntimeError("cannot open webcam")
        idx = 0
        try:
            while self.max_frames is None or idx < self.max_frames:
                t0 = time.time()
                ok, bgr = cap.read()
                if not ok:
                    return
                yield _to_frame(idx, idx / FPS, bgr)
                idx += 1
                time.sleep(max(0, 1 / FPS - (time.time() - t0)))
        finally:
            cap.release()
