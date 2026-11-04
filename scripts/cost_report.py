"""Sum tokens, calls, and $ across trace files.

Usage: .venv/bin/python scripts/cost_report.py [traces/*.jsonl]
$ requires data/prices.json {"prompt_per_mtok": X, "completion_per_mtok": Y};
without it, tokens are exact and $ is reported UNKNOWN (never guessed).
"""
from __future__ import annotations
import glob
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
CALL_EVENTS = ("router", "hazards", "rca_hypotheses", "rca_check", "retail", "wandering")


def load_prices() -> dict | None:
    p = DATA / "prices.json"
    return json.loads(p.read_text()) if p.exists() else None


def main(paths: list[str]) -> None:
    files = [f for pat in paths for f in sorted(glob.glob(pat))]
    if not files:
        print("no trace files matched")
        raise SystemExit(1)
    toks = {"prompt": 0, "completion": 0, "total": 0}
    live = cached = fallbacks = dwells = router_calls = 0
    for fn in files:
        for line in open(fn):
            e = json.loads(line)
            ev = e.get("event")
            if ev == "dwell":
                dwells += 1
            if ev in CALL_EVENTS or (ev == "rca_hypotheses"):
                meta = e.get("meta", e)
                t = e.get("tokens") or (meta.get("usage") or {})
                toks["prompt"] += t.get("prompt_tokens", t.get("prompt", 0)) or 0
                toks["completion"] += t.get("completion_tokens", t.get("completion", 0)) or 0
                toks["total"] += t.get("total_tokens", t.get("total", 0)) or 0
                if e.get("fallback", meta.get("fallback", False)):
                    fallbacks += 1
                elif e.get("cached", meta.get("cached", False)):
                    cached += 1
                else:
                    live += 1
                if ev == "router":
                    router_calls += 1
    print(f"files: {len(files)}  dwells: {dwells}  router_calls: {router_calls} "
          f"(<=1/dwell: {'OK' if router_calls <= dwells else 'VIOLATION'})")
    print(f"model calls: {live} live, {cached} cached, {fallbacks} fallbacks")
    print(f"tokens: prompt={toks['prompt']} completion={toks['completion']} total={toks['total']}")
    prices = load_prices()
    if prices:
        usd = (toks["prompt"] * prices["prompt_per_mtok"]
               + toks["completion"] * prices["completion_per_mtok"]) / 1e6
        print(f"cost: ${usd:.4f} (at {prices})")
    else:
        print("cost: $ UNKNOWN — no data/prices.json (Meta Model API pricing "
              "unpublished at build time); token counts above are exact.")


if __name__ == "__main__":
    main(sys.argv[1:] or ["traces/*.jsonl"])
