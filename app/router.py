"""Router: one Muse call per dwell -> {context, object, confidence}."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path

from .cache import ModelCache
from .llm import MODEL, InvalidError, OfflineError, complete_json

PROMPT = (Path(__file__).parent / "prompts" / "router.txt").read_text().strip()
CONTEXTS = ("manufacturing", "retail", "wandering", "unknown")


def validate_router(data: dict) -> tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "top level must be an object"
    if data.get("context") not in CONTEXTS:
        return False, f"context must be one of {CONTEXTS}"
    if not isinstance(data.get("object"), str) or not data["object"].strip():
        return False, "object must be a non-empty string"
    try:
        conf = float(data.get("confidence"))
    except (TypeError, ValueError):
        return False, "confidence must be a number 0-1"
    if not 0.0 <= conf <= 1.0:
        return False, "confidence must be a number 0-1"
    data["confidence"] = conf
    data.setdefault("object_type", "")
    data.setdefault("visible_text", "")
    if conf < 0.5:
        data["context"] = "unknown"
    return True, ""


@dataclass
class RouterResult:
    context: str
    object: str
    object_type: str = ""
    visible_text: str = ""
    confidence: float = 0.0
    meta: dict = field(default_factory=dict)


def _hints() -> str:
    # NOTE: no wall-clock time_of_day — it flips cache keys at noon/18:00/midnight
    # and breaks judges' offline replay. Deterministic env-only hint.
    loc = os.environ.get("MOCK_LOCATION", "unknown")
    return f"\nCoarse hints: mock_location_type={loc}."


def classify(image, cache: ModelCache | None = None) -> RouterResult:
    cache = cache or ModelCache()
    try:
        data, meta = complete_json(model=MODEL, prompt=PROMPT + _hints(),
                                   image=image, cache=cache, validator=validate_router,
                                   max_tokens=4000)
    except (OfflineError, InvalidError) as e:
        meta = {"cached": False, "fallback": True, "error": f"{type(e).__name__}: {e}"}
        data = {"context": "unknown", "object": "Not sure what this is",
                "object_type": "", "visible_text": "", "confidence": 0.0}
    return RouterResult(context=data["context"], object=data["object"],
                        object_type=data.get("object_type", ""),
                        visible_text=data.get("visible_text", ""),
                        confidence=data["confidence"], meta=meta)
