"""Local dwell detector. No API calls.

Dwell = frame-to-frame similarity above threshold for N consecutive frames
(downscaled grayscale mean-abs-diff), optionally ANDed with phone gyro
stillness. There is no eye tracking; the dwell target is the frame center.
"""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import asdict, dataclass

import numpy as np
from PIL import Image

from .frame_source import FPS, Frame


@dataclass
class DwellConfig:
    dwell_seconds: float = 2.5
    fps: int = FPS
    diff_threshold: float = 8.0  # mean abs diff on 0-255 scale; below = similar
    downscale: tuple[int, int] = (64, 64)
    use_gyro: bool = False

    @property
    def need(self) -> int:
        return round(self.dwell_seconds * self.fps)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["need_frames"] = self.need
        return d


@dataclass
class DwellEvent:
    frame_idx: int  # frame where the dwell completed
    t: float
    dwell_frames: int
    mean_diff: float  # avg diff over the dwell run


def _gray_small(image: Image.Image, size: tuple[int, int]) -> np.ndarray:
    return np.asarray(image.convert("L").resize(size), dtype=np.float32)


class DwellDetector:
    def __init__(self, config: DwellConfig | None = None,
                 gyro_still: Callable[[], bool] | None = None):
        self.config = config or DwellConfig()
        self.gyro_still = gyro_still
        self._prev: np.ndarray | None = None
        self._run = 0
        self._run_diffs: list[float] = []
        self._armed = True

    def update(self, frame: Frame) -> DwellEvent | None:
        cur = _gray_small(frame.image, self.config.downscale)
        if self._prev is None:
            self._prev = cur
            return None
        diff = float(np.mean(np.abs(cur - self._prev)))
        self._prev = cur
        still = diff < self.config.diff_threshold
        if self.config.use_gyro and self.gyro_still is not None:
            still = still and self.gyro_still()
        if still:
            self._run += 1
            self._run_diffs.append(diff)
        else:
            self._run = 0
            self._run_diffs = []
            self._armed = True  # motion re-arms
            return None
        if self._armed and self._run >= self.config.need:
            self._armed = False  # fire once per still period
            return DwellEvent(
                frame_idx=frame.idx, t=frame.t, dwell_frames=self._run,
                mean_diff=sum(self._run_diffs) / len(self._run_diffs),
            )
        return None
