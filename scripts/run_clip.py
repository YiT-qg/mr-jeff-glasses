"""Run a clip through frame source + dwell + (fake) router, pushing cards to the lens.

Usage: .venv/bin/python scripts/run_clip.py data/clips/x.mp4 [--fast] [--exit-when-done]
Open http://127.0.0.1:8000 for the lens simulator.
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.cache import ModelCache  # noqa: E402
from app.dwell import DwellConfig, DwellDetector  # noqa: E402
from app.frame_source import FPS, VideoFileSource, WebcamSource  # noqa: E402
from app.router import classify  # noqa: E402
from app.rca import RcaState  # noqa: E402
from app.server import start_in_thread, wait_ready  # noqa: E402
from app.specialists.manufacturing import RcaDriver, detect_hazards  # noqa: E402
from app.specialists.retail import identify as identify_retail  # noqa: E402
from app.specialists.wandering import identify as identify_wandering  # noqa: E402


def fake_router(dwell_idx: int, frame_idx: int, dwell_frames: int) -> dict:
    return {
        "title": f"Dwell #{dwell_idx} @ f{frame_idx}",
        "lines": ["FAKE router (Phase 2)", f"view static {dwell_frames} frames", "Space = pinch"],
        "step": f"Card {dwell_idx}",
    }


def usage_tokens(usage: dict | None) -> dict:
    usage = usage or {}
    return {"prompt": usage.get("prompt_tokens", 0), "completion": usage.get("completion_tokens", 0),
            "total": usage.get("total_tokens", 0)}


def post_action(port: int, card: dict, ev: dict, log, stats: dict) -> None:
    r = requests.post(f"http://127.0.0.1:{port}/card", json=card, timeout=5)
    r.raise_for_status()
    stats["cards"] += 1
    log(**ev, card_id=r.json()["id"])
    if ev.get("event") == "rca_unavailable":
        stats["fallbacks"] += 1
    print(f"  RCA {ev['event']}: {card['title']}")


def tally_meta(meta: dict, stats: dict) -> None:
    if meta.get("cached"):
        stats["cached"] += 1
    elif meta.get("fallback"):
        stats["fallbacks"] += 1
    else:
        stats["api_calls"] += 1
    for k, v in usage_tokens(meta.get("usage")).items():
        stats["tokens"][k] += v or 0


def handle_live_dwell(dwell_idx: int, event, frame, port: int, cache: ModelCache,
                      driver: RcaDriver, log, stats: dict) -> None:
    result = classify(frame.image, cache)
    meta = result.meta
    if meta.get("cached"):
        stats["cached"] += 1
    elif meta.get("fallback"):
        stats["fallbacks"] += 1
    else:
        stats["api_calls"] += 1
    toks = usage_tokens(meta.get("usage"))
    for k, v in toks.items():
        stats["tokens"][k] += v or 0
    log(event="router", frame_idx=event.frame_idx, model=meta.get("model", "?"),
        latency_ms=meta.get("latency_ms"), cached=meta.get("cached", False),
        fallback=meta.get("fallback", False), error=meta.get("error"), tokens=toks,
        context=result.context, object=result.object, confidence=result.confidence)
    if meta.get("fallback"):
        print(f"  router FALLBACK: {meta.get('error')}")
    card = {"title": f"{result.object} · {result.context}",
            "lines": [f"reads: {result.visible_text}" if result.visible_text else "reads: (nothing)",
                      f"conf {result.confidence:.2f}"],
            "step": f"Dwell {dwell_idx}"}
    r = requests.post(f"http://127.0.0.1:{port}/card", json=card, timeout=5)
    r.raise_for_status()
    stats["cards"] += 1
    log(event="card", card_id=r.json()["id"], frame_idx=event.frame_idx,
        title=card["title"], model=meta.get("model", "?"))
    print(f"dwell #{dwell_idx} @ frame {event.frame_idx} -> {result.context}: {result.object} "
          f"(cached={meta.get('cached', False)})")
    feeding = result.context == "manufacturing" and not meta.get("fallback")
    if feeding:
        hz = detect_hazards(frame.image, cache)
        hmeta = hz.meta
        if hmeta.get("cached"):
            stats["cached"] += 1
        elif hmeta.get("fallback"):
            stats["fallbacks"] += 1
        else:
            stats["api_calls"] += 1
        htoks = usage_tokens(hmeta.get("usage"))
        for k, v in htoks.items():
            stats["tokens"][k] += v or 0
        log(event="hazards", frame_idx=event.frame_idx, model=hmeta.get("model", "?"),
            latency_ms=hmeta.get("latency_ms"), cached=hmeta.get("cached", False),
            fallback=hmeta.get("fallback", False), error=hmeta.get("error"), tokens=htoks,
            hazards=[h.__dict__ for h in hz.hazards])
        if hmeta.get("fallback"):
            print(f"  hazards FALLBACK: {hmeta.get('error')}")
        for i, h in enumerate(hz.hazards, 1):
            hcard = {"title": f"HAZARD: {h.type}", "lines": [h.where, "Advisory — verify before acting"],
                     "step": f"Hazard {i}/{len(hz.hazards)}"}
            r = requests.post(f"http://127.0.0.1:{port}/card", json=hcard, timeout=5)
            r.raise_for_status()
            stats["cards"] += 1
            log(event="card", card_id=r.json()["id"], frame_idx=event.frame_idx,
                title=hcard["title"], model=hmeta.get("model", "?"), priority="hazard")
            print(f"  HAZARD: {h.type} — {h.where}")
    session_open = (driver.session is not None
                    and driver.session.state in (RcaState.HYPOTHESES, RcaState.CHECKS))
    if feeding or (session_open and result.context == "unknown"):
        actions, rmetas = driver.on_dwell(result, frame.image, event.frame_idx)
        for card, ev in actions:
            post_action(port, card, ev, log, stats)
        for m in rmetas:
            tally_meta(m, stats)
    if result.context == "retail" and not meta.get("fallback"):
        rr = identify_retail(frame.image, cache)
        rmeta = rr.meta
        tally_meta(rmeta, stats)
        if rmeta.get("fallback"):
            log(event="retail", frame_idx=event.frame_idx, fallback=True,
                error=rmeta.get("error"))
            print(f"  retail FALLBACK: {rmeta.get('error')}")
        else:
            lines = [f"~${rr.price_guess:.0f}"]
            lines += [f"{a['product']} ${a['price']}" for a in rr.alternatives[:2]]
            card = {"title": rr.product[:56], "lines": lines[:3], "step": "Retail"}
            r = requests.post(f"http://127.0.0.1:{port}/card", json=card, timeout=5)
            r.raise_for_status()
            stats["cards"] += 1
            log(event="retail", card_id=r.json()["id"], frame_idx=event.frame_idx,
                model=rmeta.get("model", "?"), latency_ms=rmeta.get("latency_ms"),
                cached=rmeta.get("cached", False), tokens=usage_tokens(rmeta.get("usage")),
                product=rr.product, price_guess=rr.price_guess,
                alternatives=rr.alternatives)
            print(f"  retail: {rr.product} ({len(rr.alternatives)} alternatives)")
    if result.context == "wandering" and not meta.get("fallback"):
        wr = identify_wandering(frame.image, cache)
        wmeta = wr.meta
        tally_meta(wmeta, stats)
        if wmeta.get("fallback"):
            log(event="wandering", frame_idx=event.frame_idx, fallback=True,
                error=wmeta.get("error"))
            print(f"  wandering FALLBACK: {wmeta.get('error')}")
        else:
            lines = [wr.direction] if wr.direction else ["Set MOCK_DESTINATION", "for directions"]
            card = {"title": wr.place[:56], "lines": lines[:3], "step": "Wandering"}
            r = requests.post(f"http://127.0.0.1:{port}/card", json=card, timeout=5)
            r.raise_for_status()
            stats["cards"] += 1
            log(event="wandering", card_id=r.json()["id"], frame_idx=event.frame_idx,
                model=wmeta.get("model", "?"), latency_ms=wmeta.get("latency_ms"),
                cached=wmeta.get("cached", False), tokens=usage_tokens(wmeta.get("usage")),
                place=wr.place, direction=wr.direction)
            print(f"  wandering: {wr.place}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", help="video file, or 'webcam'")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--fast", action="store_true", help="no realtime pacing")
    ap.add_argument("--exit-when-done", action="store_true")
    ap.add_argument("--router", choices=("live", "fake"), default="live",
                    help="live = Muse calls with cache (default); fake = canned cards")
    args = ap.parse_args()

    server = start_in_thread(port=args.port)
    wait_ready(args.port)
    print(f"lens: http://127.0.0.1:{args.port}")

    traces = Path("traces")
    traces.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = "webcam" if args.clip == "webcam" else Path(args.clip).stem
    trace_path = traces / f"{name}_{stamp}.jsonl"
    trace = trace_path.open("w")

    def log(**kw):
        trace.write(json.dumps(kw) + "\n")
        trace.flush()

    config = DwellConfig()
    log(event="config", dwell=config.to_dict(), source=args.clip, router=args.router)
    print(f"dwell: need={config.need} frames @ {config.fps}fps, threshold={config.diff_threshold}")

    source = WebcamSource(max_frames=150) if args.clip == "webcam" else VideoFileSource(args.clip)
    detector = DwellDetector(config)
    cache = ModelCache()
    driver = RcaDriver(cache)
    seen_pinches = 0
    stats = {"dwells": 0, "cards": 0, "api_calls": 0, "cached": 0, "fallbacks": 0,
             "tokens": {"prompt": 0, "completion": 0, "total": 0}}
    for frame in source:
        t0 = time.time()
        event = detector.update(frame)
        if event is not None:
            stats["dwells"] += 1
            log(event="dwell", frame_idx=event.frame_idx, t=round(event.t, 2),
                dwell_frames=event.dwell_frames, mean_diff=round(event.mean_diff, 3))
            if args.router == "fake":
                card = fake_router(stats["dwells"], event.frame_idx, event.dwell_frames)
                r = requests.post(f"http://127.0.0.1:{args.port}/card", json=card, timeout=5)
                r.raise_for_status()
                stats["cards"] += 1
                log(event="card", card_id=r.json()["id"], frame_idx=event.frame_idx,
                    title=card["title"], model="fake")
                print(f"dwell #{stats['dwells']} @ frame {event.frame_idx} -> card #{r.json()['id']}")
            else:
                handle_live_dwell(stats["dwells"], event, frame, args.port, cache,
                                  driver, log, stats)
        if driver.session is not None and driver.session.state != RcaState.CLOSE:
            try:
                pinches = requests.get(f"http://127.0.0.1:{args.port}/pinches",
                                       timeout=2).json()["pinches"]
            except requests.RequestException:
                pinches = None
            if pinches is not None and len(pinches) > seen_pinches:
                seen_pinches = len(pinches)
                actions, _ = driver.on_pinch(frame.idx)
                for card, ev in actions:
                    post_action(args.port, card, ev, log, stats)
        if not args.fast:
            time.sleep(max(0, 1 / FPS - (time.time() - t0)))
    log(event="summary", dwells=stats["dwells"], cards=stats["cards"], api_calls=stats["api_calls"],
        cached=stats["cached"], fallbacks=stats["fallbacks"], tokens=stats["tokens"],
        cost_usd=None, cost_note="$ TBD, see PROBE_NOTES.md")
    trace.close()
    print(f"done: {stats['dwells']} dwells, {stats['cards']} cards, "
          f"{stats['api_calls']} live calls ({stats['cached']} cached, {stats['fallbacks']} fallbacks), "
          f"tokens={stats['tokens']}, trace={trace_path}")
    if args.exit_when_done:
        server.should_exit = True
    else:
        print("server still up for lens review; Ctrl-C to stop.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            server.should_exit = True


if __name__ == "__main__":
    main()
