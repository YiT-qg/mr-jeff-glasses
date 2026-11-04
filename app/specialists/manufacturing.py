"""Manufacturing specialist, Phase 3 slice: hazard detection only.

Hazards always run first in manufacturing and pre-empt every other card.
Advisory only — never a replacement for LOTO or machine guarding.
(RCA + work orders land in Phase 4/5.)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

from ..cache import ModelCache
from ..llm import MODEL, InvalidError, OfflineError, complete_json
from ..mrjeff_client import create_work_order
from ..rca import (NO_PROCEDURE, RcaState, append_history, close_session, confirm_current,
                   current_check, find_code, match_asset, parts_for, start_session,
                   submit_check)

PROMPT = (Path(__file__).parent.parent / "prompts" / "manufacturing_hazards.txt").read_text().strip()
ALLOWED = ("missing eye protection", "missing hard hat",
           "person inside a marked keep-out zone", "spill or blocked walkway",
           "removed machine guard")


def validate_hazards(data: dict) -> tuple[bool, str]:
    if not isinstance(data, dict) or not isinstance(data.get("hazards"), list):
        return False, "top level must be {hazards: [...]}"
    for h in data["hazards"]:
        if not isinstance(h, dict) or h.get("type") not in ALLOWED:
            return False, f"hazard type must be one of {ALLOWED}"
        if not isinstance(h.get("where"), str):
            return False, "hazard.where must be a string"
        try:
            conf = float(h.get("confidence"))
        except (TypeError, ValueError):
            return False, "hazard.confidence must be a number 0-1"
        if not 0.0 <= conf <= 1.0:
            return False, "hazard.confidence must be a number 0-1"
        h["confidence"] = conf
    return True, ""


@dataclass
class Hazard:
    type: str
    where: str
    confidence: float


@dataclass
class HazardsResult:
    hazards: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def detect_hazards(image, cache: ModelCache | None = None) -> HazardsResult:
    cache = cache or ModelCache()
    try:
        data, meta = complete_json(model=MODEL, prompt=PROMPT, image=image,
                                   cache=cache, validator=validate_hazards,
                                   max_tokens=4000)
    except (OfflineError, InvalidError) as e:
        return HazardsResult(hazards=[], meta={"fallback": True,
                             "error": f"{type(e).__name__}: {e}"})
    return HazardsResult(hazards=[Hazard(**h) for h in data["hazards"]], meta=meta)


def _short(s: str, n: int = 56) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


class RcaDriver:
    """Owns one RCA session. Returns (actions, new_call_metas) per event.

    Each action is (card_dict, trace_event_dict); the caller posts the card
    and logs the event with the card id.
    """

    def __init__(self, cache: ModelCache | None = None):
        self.cache = cache or ModelCache()
        self.session = None

    def _fix_actions(self, frame_idx: int) -> list:
        s = self.session
        if not s.manual:
            card = {"title": "No procedure on file", "lines": ["Call maintenance lead."],
                    "step": "Fix"}
            return [(card, {"event": "rca_fix", "frame_idx": frame_idx, "manual": None})]
        steps = s.manual["steps"]
        actions = []
        for i, step in enumerate(steps, 1):
            card = {"title": f"Fix · {s.code}", "lines": [_short(step, 64)],
                    "step": f"Step {i}/{len(steps)}"}
            actions.append((card, {"event": "rca_fix", "frame_idx": frame_idx,
                                   "step": i, "of": len(steps), "text": step}))
        parts = parts_for(s.asset_id, s.root_cause)
        plines = [f"{p['part']}: {p['stock']} in stock, Bin {p['bin']}" for p in parts[:3]]
        card = {"title": f"Parts · {s.asset_id}", "lines": plines or ["No parts listed"],
                "step": "Parts"}
        actions.append((card, {"event": "rca_parts", "frame_idx": frame_idx, "parts": parts}))
        return actions

    def _start(self, asset: dict, code: str, frame_image, frame_idx: int) -> tuple:
        try:
            self.session = s = start_session(asset, code, frame_image, self.cache)
        except (OfflineError, InvalidError) as e:
            card = {"title": "Diagnosis unavailable",
                    "lines": ["Check connection, or", "call maintenance lead."], "step": "RCA"}
            return [(card, {"event": "rca_unavailable", "frame_idx": frame_idx,
                            "error": f"{type(e).__name__}: {e}"})], []
        meta = s.metas[-1]
        n = len(s.hypotheses)
        cards = [
            ({"title": f"{s.symptom_title} · {s.asset_id}",
              "lines": [f"{len(asset.get('work_orders', []))} past work orders reviewed"],
              "step": "Symptom"},
             {"event": "rca_symptom", "frame_idx": frame_idx, "asset": s.asset_id,
              "code": s.code, "symptom": s.symptom_title}),
            ({"title": f"{n} hypotheses · {s.code}",
              "lines": [f"{i + 1}. {_short(h.cause, 34)}" for i, h in
                        enumerate(s.hypotheses[:3])],
              "step": "Hypotheses"},
             {"event": "rca_hypotheses", "frame_idx": frame_idx,
              "hypotheses": [h.__dict__ for h in s.hypotheses], "meta": meta}),
        ]
        first = current_check(s)
        cards.append(({"title": "Check 1/%d" % n, "lines": [_short(first.check, 64)],
                       "step": "Check 1/%d" % n},
                      {"event": "rca_check_prompt", "frame_idx": frame_idx,
                       "check": first.check}))
        return cards, [meta]

    def _submit(self, frame_image, frame_idx: int) -> tuple:
        s = self.session
        num = s.check_idx + 1  # the check being judged (unclear verdicts don't advance)
        try:
            rec = submit_check(s, frame_image, self.cache)
        except (OfflineError, InvalidError) as e:
            card = {"title": "Check unavailable", "lines": ["Pinch to confirm by hand."],
                    "step": "RCA"}
            return [(card, {"event": "rca_unavailable", "frame_idx": frame_idx,
                            "error": f"{type(e).__name__}: {e}"})], []
        meta = s.metas[-1]
        mark = {"confirmed": "✓", "ruled_out": "✗", "unclear": "?"}[rec.result]
        total = len(s.hypotheses)
        actions = [({"title": f"{mark} {rec.result.replace('_', ' ').title()}",
                     "lines": [_short(rec.hypothesis, 48), _short(rec.evidence, 56)],
                     "step": f"Check {num}/{total}"},
                    {"event": "rca_check", "frame_idx": frame_idx,
                     "check": rec.__dict__, "meta": meta})]
        if s.state == RcaState.ROOT_CAUSE_FIX:
            actions += self._fix_actions(frame_idx)
        elif s.state == RcaState.CLOSE:
            payload = close_session(s)
            actions.append(({"title": "No cause confirmed",
                             "lines": ["Call maintenance lead."], "step": "Close"},
                            {"event": "rca_close", "frame_idx": frame_idx,
                             "payload": payload}))
        else:
            nxt = current_check(s)
            cur = s.check_idx + 1
            actions.append(({"title": f"Check {cur}/{total}",
                             "lines": [_short(nxt.check, 64)], "step": f"Check {cur}/{total}"},
                            {"event": "rca_check_prompt", "frame_idx": frame_idx,
                             "check": nxt.check}))
        return actions, [meta]

    def on_dwell(self, router_result, frame_image, frame_idx: int) -> tuple:
        s = self.session
        if s is not None and s.state in (RcaState.HYPOTHESES, RcaState.CHECKS):
            # Check spots don't show the asset/code; any manufacturing dwell feeds the check.
            return self._submit(frame_image, frame_idx)
        asset = match_asset(router_result.visible_text or "", router_result.object or "")
        code = find_code(router_result.visible_text or "")
        if asset is None or code is None:
            return [], []
        if s is None or s.state == RcaState.CLOSE or (s.asset_id, s.code) != (asset["id"], code):
            return self._start(asset, code, frame_image, frame_idx)
        return [], []

    def on_pinch(self, frame_idx: int = -1) -> tuple:
        s = self.session
        if s is None:
            return [], []
        if s.state in (RcaState.HYPOTHESES, RcaState.CHECKS):
            confirm_current(s)
            return self._fix_actions(frame_idx), []
        if s.state == RcaState.ROOT_CAUSE_FIX:
            payload = close_session(s)
            wo = create_work_order(payload)
            n = append_history(s.asset_id, s.code,
                               f"RCA: {s.root_cause} ({len(s.checks)} checks performed).",
                               wo["id"])
            card = {"title": f"Work order {wo['id']} created",
                    "lines": [_short(s.root_cause or "unresolved", 56),
                              ("via Mr. Jeff API" if wo["via"] == "api" else "via local log")
                              + f" · {n} WOs in history"],
                    "step": "Close"}
            logged = {k: v for k, v in payload.items() if k != "frame_jpeg_b64"}
            logged["frame"] = "jpeg_b64 in WO record" if payload.get("frame_jpeg_b64") else None
            return [(card, {"event": "rca_close", "frame_idx": frame_idx, "wo": wo,
                            "history_wos": n, "payload": logged})], []
        return [], []
