"""Wandering specialist (light): place ID + mock directions to a destination."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path

from ..cache import ModelCache
from ..llm import MODEL, InvalidError, OfflineError, complete_json

PROMPT = (Path(__file__).parent.parent / "prompts" / "wandering.txt").read_text().strip()


def validate_wandering(data: dict) -> tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "top level must be an object"
    if not isinstance(data.get("place"), str) or not data["place"].strip():
        return False, "place must be a non-empty string"
    if not isinstance(data.get("direction"), str):
        return False, "direction must be a string"
    return True, ""


@dataclass
class WanderingResult:
    place: str
    direction: str = ""
    meta: dict = field(default_factory=dict)


def identify(image, cache: ModelCache | None = None) -> WanderingResult:
    cache = cache or ModelCache()
    loc = os.environ.get("MOCK_LOCATION", "unknown")
    dest = os.environ.get("MOCK_DESTINATION", "") or "(none)"
    prompt = f"{PROMPT}\nMock location: {loc}. Destination: {dest}."
    try:
        data, meta = complete_json(model=MODEL, prompt=prompt, image=image,
                                   cache=cache, validator=validate_wandering,
                                   max_tokens=4000)
    except (OfflineError, InvalidError) as e:
        return WanderingResult(place="", meta={"fallback": True,
                               "error": f"{type(e).__name__}: {e}"})
    return WanderingResult(place=data["place"], direction=data["direction"], meta=meta)
