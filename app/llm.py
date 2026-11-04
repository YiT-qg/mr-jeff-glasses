"""Shared single-image JSON completion: cache first, one live call, one retry.

Every model call in the app goes through complete_json so caching, JSON repair,
and the offline fallback behave the same everywhere.
"""
from __future__ import annotations
import base64
import io
import json
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

from .cache import ModelCache, cache_key

BASE = os.environ.get("MODEL_API_BASE", "https://api.meta.ai/v1")
MODEL = "muse-spark-1.3"


class OfflineError(Exception):
    """No cached response and live calls unavailable (no key or MRJEFF_OFFLINE=1)."""


class InvalidError(Exception):
    """Model output failed validation twice."""


def frame_jpeg(image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object found")
    return json.loads(text[start : end + 1])


def _post(model: str, prompt: str, img_b64: str, max_tokens: int) -> tuple[dict, dict]:
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                ],
            }
        ],
    }
    t0 = time.time()
    r = requests.post(
        f"{BASE}/chat/completions",
        headers={"Authorization": f"Bearer {os.environ.get('MODEL_API_KEY', '')}"},
        json=body,
        timeout=120,
    )
    latency_ms = round((time.time() - t0) * 1000)
    data = r.json()
    if r.status_code != 200:
        raise InvalidError(f"HTTP {r.status_code}: {json.dumps(data)[:200]}")
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise InvalidError(f"bad chat shape: {json.dumps(data)[:200]}")
    if not content:
        raise InvalidError("empty content (finish_reason=%s)" % data["choices"][0].get("finish_reason"))
    return _extract_json(content), {"latency_ms": latency_ms, "usage": data.get("usage")}


def complete_json(*, model: str, prompt: str, image, cache: ModelCache,
                  validator, max_tokens: int = 1000) -> tuple[dict, dict]:
    """Returns (validated_data, meta). Raises OfflineError / InvalidError."""
    img_bytes = frame_jpeg(image)
    key = cache_key(model, prompt, img_bytes)
    if not cache.off_switch:
        hit = cache.get(key)
        if hit is not None:
            return hit["data"], {"cached": True, "latency_ms": 0,
                                 "usage": hit.get("usage"), "model": model}
    if os.environ.get("MRJEFF_OFFLINE") == "1" or not os.environ.get("MODEL_API_KEY"):
        raise OfflineError(key)
    img_b64 = base64.b64encode(img_bytes).decode()
    data, meta = _post(model, prompt, img_b64, max_tokens)
    ok, err = validator(data)
    if not ok:  # retry once with the validation error
        data, meta = _post(model, prompt + f"\nYour previous reply was invalid: {err}. Fix it.",
                           img_b64, max_tokens)
        ok, err = validator(data)
        if not ok:
            raise InvalidError(err)
    meta.update({"cached": False, "model": model})
    if not cache.off_switch:
        cache.set(key, model, {"data": data, "usage": meta.get("usage")})
    return data, meta
