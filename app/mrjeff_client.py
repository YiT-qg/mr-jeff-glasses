"""Mr. Jeff work-order write-back: live API when MRJEFF_API_URL is set, else JSONL."""
from __future__ import annotations
import json
import os
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

DATA = Path(__file__).resolve().parent.parent / "data"
LEDGER = DATA / "work_orders.jsonl"


def _next_id() -> str:
    n = 0
    if LEDGER.exists():
        for line in LEDGER.read_text().splitlines():
            try:
                n = max(n, int(json.loads(line).get("id", "WO-0000").split("-")[1]))
            except (ValueError, IndexError):
                pass
    return f"WO-{n + 1:04d}"


def create_work_order(record: dict) -> dict:
    """Persist a work order. Returns {"id", "via"}.

    Tries POST to MRJEFF_API_URL first; on any failure falls back to the local
    JSONL ledger so a work order is never lost.
    """
    record = {"created_at": time.time(), "date": date.today().isoformat(), **record}
    url = os.environ.get("MRJEFF_API_URL", "").strip()
    if url:
        try:
            r = requests.post(url, json=record, timeout=15)
            r.raise_for_status()
            try:
                rid = r.json().get("id")
            except ValueError:
                rid = None
            return {"id": rid or f"REMOTE-{int(time.time())}", "via": "api"}
        except requests.RequestException:
            pass
    record["id"] = _next_id()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps(record) + "\n")
    return {"id": record["id"], "via": "jsonl"}
