"""Retail specialist (light): product ID + up to 2 cheaper catalog alternatives."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..cache import ModelCache
from ..llm import MODEL, InvalidError, OfflineError, complete_json

PROMPT = (Path(__file__).parent.parent / "prompts" / "retail.txt").read_text().strip()
DATA = Path(__file__).parent.parent.parent / "data"


def load_catalog() -> list[dict]:
    return json.loads((DATA / "products.json").read_text())["products"]


def validate_retail(data: dict) -> tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "top level must be an object"
    if not isinstance(data.get("product"), str) or not data["product"].strip():
        return False, "product must be a non-empty string"
    try:
        data["price_guess"] = float(data.get("price_guess"))
    except (TypeError, ValueError):
        return False, "price_guess must be a number"
    alts = data.get("alternatives")
    if not isinstance(alts, list) or len(alts) > 2:
        return False, "alternatives must be a list of at most 2"
    for a in alts:
        if not isinstance(a, dict) or not isinstance(a.get("product"), str):
            return False, "each alternative needs a product name"
    return True, ""


def ground(alts: list[dict], price_guess: float) -> list[dict]:
    """Keep only alternatives that exist in the catalog and are cheaper."""
    catalog = {p["name"].lower(): p for p in load_catalog()}
    out = []
    for a in alts:
        hit = catalog.get(a["product"].strip().lower())
        if hit and hit["price"] < price_guess:
            out.append({"product": hit["name"], "price": hit["price"]})
    return out[:2]


@dataclass
class RetailResult:
    product: str
    price_guess: float = 0.0
    alternatives: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def identify(image, cache: ModelCache | None = None) -> RetailResult:
    cache = cache or ModelCache()
    prompt = f"{PROMPT}\nCatalog:\n{json.dumps(load_catalog())}"
    try:
        data, meta = complete_json(model=MODEL, prompt=prompt, image=image,
                                   cache=cache, validator=validate_retail,
                                   max_tokens=4000)
    except (OfflineError, InvalidError) as e:
        return RetailResult(product="", meta={"fallback": True,
                            "error": f"{type(e).__name__}: {e}"})
    return RetailResult(product=data["product"], price_guess=data["price_guess"],
                        alternatives=ground(data["alternatives"], data["price_guess"]),
                        meta=meta)
