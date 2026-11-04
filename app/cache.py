"""Record/replay cache for model calls, keyed by sha256(model + prompt + image).

Live calls record; demo and judges' runs replay with no key and $0 cost.
"""
from __future__ import annotations
import hashlib
import json
import os
import time
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


def cache_key(model: str, prompt: str, image_bytes: bytes) -> str:
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(b"\x00")
    h.update(prompt.encode())
    h.update(b"\x00")
    h.update(image_bytes)
    return h.hexdigest()


class ModelCache:
    def __init__(self, directory: str | Path = DEFAULT_DIR):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> dict | None:
        p = self._path(key)
        if not p.exists():
            self.misses += 1
            return None
        self.hits += 1
        return json.loads(p.read_text())["value"]

    def set(self, key: str, model: str, value: dict) -> None:
        record = {"key": key, "model": model, "recorded_at": time.time(), "value": value}
        self._path(key).write_text(json.dumps(record))

    @property
    def off_switch(self) -> bool:
        return os.environ.get("MRJEFF_NO_CACHE") == "1"
