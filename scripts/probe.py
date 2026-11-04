"""Phase 1 probe: send one synthetic image to muse-spark-1.3 and sam-3.1.

Prints response shape, token usage, and latency for budgeting.
Usage: MODEL_API_KEY=... .venv/bin/python scripts/probe.py
"""
import base64
import io
import json
import os
import sys
import time

import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw

load_dotenv()
BASE = "https://api.meta.ai/v1"
KEY = os.environ.get("MODEL_API_KEY", "")


def make_image() -> bytes:
    img = Image.new("RGB", (504, 896), (38, 38, 44))
    d = ImageDraw.Draw(img)
    d.rectangle([150, 350, 354, 450], fill=(200, 60, 60))
    d.text((160, 390), "PROBE E-204", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def probe(model: str, img_b64: str) -> dict:
    body = {
        "model": model,
        "max_tokens": 1000,  # reasoning tokens eat the completion budget; 200 left content=null
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image in one line. Reply in JSON: {\"seen\": string}."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                ],
            }
        ],
    }
    t0 = time.time()
    r = requests.post(
        f"{BASE}/chat/completions",
        headers={"Authorization": f"Bearer {KEY}"},
        json=body,
        timeout=90,
    )
    dt = (time.time() - t0) * 1000
    out = {"model": model, "status": r.status_code, "latency_ms": round(dt)}
    try:
        data = r.json()
    except ValueError:
        out["body_preview"] = r.text[:300]
        return out
    out["top_keys"] = list(data.keys())[:10]
    out["usage"] = data.get("usage")
    try:
        content = data["choices"][0]["message"]["content"]
        out["content_preview"] = content[:300]
    except (KeyError, IndexError, TypeError):
        out["error_preview"] = json.dumps(data)[:300]
    return out


def probe_responses(model: str, img_b64: str) -> dict:
    # API directed sam-3.1 here (404 on /chat/completions said "Use /v1/responses").
    # Trying the Responses-style shape once; prints whatever comes back.
    body = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Segment the red panel. Reply in JSON: {\"seen\": string}."},
                    {"type": "input_image", "image_url": f"data:image/jpeg;base64,{img_b64}"},
                ],
            }
        ],
    }
    t0 = time.time()
    r = requests.post(f"{BASE}/responses", headers={"Authorization": f"Bearer {KEY}"}, json=body, timeout=90)
    dt = (time.time() - t0) * 1000
    out = {"model": model, "endpoint": "/v1/responses", "status": r.status_code, "latency_ms": round(dt)}
    try:
        data = r.json()
    except ValueError:
        out["body_preview"] = r.text[:300]
        return out
    out["top_keys"] = list(data.keys())[:10]
    out["usage"] = data.get("usage")
    out["body_preview"] = json.dumps(data)[:500]
    return out


def mock_result(model: str) -> dict:
    return {
        "model": model,
        "status": 200,
        "latency_ms": "mock",
        "top_keys": ["id", "object", "created", "model", "choices", "usage"],
        "usage": {"prompt_tokens": "mock", "completion_tokens": "mock", "total_tokens": "mock"},
        "content_preview": '{"seen": "red panel with PROBE E-204 text (MOCK)"}',
        "note": "MOCK - no API call made. Re-run with MODEL_API_KEY for real numbers.",
    }


def main() -> None:
    mock = os.environ.get("MOCK") == "1" or "--mock" in sys.argv
    img_b64 = base64.b64encode(make_image()).decode()
    print(f"image bytes: {len(img_b64) * 3 // 4}, b64 chars: {len(img_b64)}")
    if mock:
        for model in ("muse-spark-1.3", "sam-3.1"):
            print(json.dumps(mock_result(model), indent=2))
        return
    if not KEY:
        print("ERROR: MODEL_API_KEY is empty. Options:")
        print("  1. MODEL_API_KEY=... .venv/bin/python scripts/probe.py   (live, spends a few cents)")
        print("  2. MOCK=1 .venv/bin/python scripts/probe.py              (offline, fake numbers)")
        raise SystemExit(2)
    print(json.dumps(probe("muse-spark-1.3", img_b64), indent=2))
    print(json.dumps(probe_responses("sam-3.1", img_b64), indent=2))


if __name__ == "__main__":
    main()
