"""RCA state machine: SYMPTOM -> HYPOTHESES -> CHECKS -> ROOT_CAUSE_FIX -> CLOSE.

Fix steps come only from data/manuals/. If no manual matches, the flow ends
with "No procedure on file. Call maintenance lead."
"""
from __future__ import annotations
import base64
import json
import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path

from .cache import ModelCache
from .llm import MODEL, complete_json, frame_jpeg

PROMPTS = Path(__file__).parent / "prompts"
HYP_PROMPT = (PROMPTS / "rca_hypotheses.txt").read_text().strip()
CHECK_PROMPT = (PROMPTS / "rca_check.txt").read_text().strip()
DATA = Path(__file__).parent.parent / "data"
NO_PROCEDURE = "No procedure on file. Call maintenance lead."


class RcaState(Enum):
    SYMPTOM = "SYMPTOM"
    HYPOTHESES = "HYPOTHESES"
    CHECKS = "CHECKS"
    ROOT_CAUSE_FIX = "ROOT_CAUSE_FIX"
    CLOSE = "CLOSE"


@dataclass
class Hypothesis:
    cause: str
    reason_from_history: str
    check: str


@dataclass
class CheckRecord:
    hypothesis: str
    check: str
    result: str  # confirmed | ruled_out | unclear | manual
    evidence: str


def validate_hypotheses(data: dict) -> tuple[bool, str]:
    hyps = data.get("hypotheses") if isinstance(data, dict) else None
    if not isinstance(hyps, list) or not 1 <= len(hyps) <= 3:
        return False, "hypotheses must be a list of 1-3 items"
    for h in hyps:
        if not isinstance(h, dict):
            return False, "each hypothesis must be an object"
        for k in ("cause", "reason_from_history", "check"):
            if not isinstance(h.get(k), str) or not h[k].strip():
                return False, f"hypothesis.{k} must be a non-empty string"
    return True, ""


def validate_check(data: dict) -> tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "top level must be an object"
    if data.get("result") not in ("confirmed", "ruled_out", "unclear"):
        return False, "result must be confirmed|ruled_out|unclear"
    if not isinstance(data.get("evidence"), str):
        return False, "evidence must be a string"
    return True, ""


def load_assets() -> dict[str, dict]:
    return {a["id"]: a for a in json.loads((DATA / "assets.json").read_text())["assets"]}


def match_asset(visible_text: str, object: str) -> dict | None:
    hay = f"{visible_text} {object}".upper()
    for aid, asset in load_assets().items():
        if aid.upper() in hay:
            return asset
    return None


def find_code(visible_text: str) -> str | None:
    m = re.search(r"\b([A-Z]-\d{2,4})\b", visible_text.upper())
    return m.group(1) if m else None


def load_manual(code: str) -> dict | None:
    p = DATA / "manuals" / f"{code}.md"
    if not p.exists():
        return None
    title, steps = code, []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line.startswith("# "):
            title = line[2:].strip()
        else:
            m = re.match(r"^\d+\.\s+(.*)$", line)
            if m:
                steps.append(m.group(1).strip())
    return {"code": code, "title": title, "steps": steps} if steps else None


@dataclass
class RcaSession:
    asset_id: str
    code: str
    symptom_title: str
    state: RcaState = RcaState.SYMPTOM
    hypotheses: list = field(default_factory=list)
    check_idx: int = 0
    checks: list = field(default_factory=list)
    root_cause: str | None = None
    manual: dict | None = None
    metas: list = field(default_factory=list)
    frame_jpeg: bytes | None = None  # symptom dwell frame, attached to the WO


def append_history(asset_id: str, code: str, summary: str, wo_id: str) -> int:
    """Append a work order to the asset's history. Returns the new WO count.

    The entry is stamped "today" (literal) instead of a calendar date so the
    post-WO hypotheses prompt is identical on any run date and its recording
    replays for judges offline.
    """
    p = DATA / "assets.json"
    data = json.loads(p.read_text())
    n = 0
    for a in data["assets"]:
        if a["id"] == asset_id:
            a["work_orders"].append({"date": "today", "code": code,
                                    "summary": summary, "wo_id": wo_id})
            n = len(a["work_orders"])
    p.write_text(json.dumps(data, indent=1) + "\n")
    return n


def start_session(asset: dict, code: str, frame_image, cache: ModelCache) -> RcaSession:
    manual = load_manual(code)
    symptom_title = manual["title"] if manual else code
    history = {k: asset[k] for k in ("id", "type", "pm", "work_orders", "notes") if k in asset}
    prompt = (f"{HYP_PROMPT}\nSymptom: {code} {symptom_title} on {asset['id']}.\n"
              f"Machine work-order history:\n{json.dumps(history)}")
    data, meta = complete_json(model=MODEL, prompt=prompt, image=frame_image,
                               cache=cache, validator=validate_hypotheses, max_tokens=4000)
    session = RcaSession(asset_id=asset["id"], code=code, symptom_title=symptom_title,
                         state=RcaState.CHECKS, manual=manual,
                         frame_jpeg=frame_jpeg(frame_image))
    session.hypotheses = [Hypothesis(**h) for h in data["hypotheses"]]
    session.metas.append({"call": "hypotheses", **meta})
    session.state = RcaState.HYPOTHESES
    return session


def current_check(session: RcaSession) -> Hypothesis | None:
    if session.check_idx < len(session.hypotheses):
        return session.hypotheses[session.check_idx]
    return None


def submit_check(session: RcaSession, frame_image, cache: ModelCache) -> CheckRecord:
    hyp = current_check(session)
    prompt = CHECK_PROMPT.replace("{cause}", hyp.cause).replace("{check}", hyp.check)
    data, meta = complete_json(model=MODEL, prompt=prompt, image=frame_image,
                               cache=cache, validator=validate_check, max_tokens=4000)
    rec = CheckRecord(hypothesis=hyp.cause, check=hyp.check,
                      result=data["result"], evidence=data["evidence"])
    session.checks.append(rec)
    session.metas.append({"call": "check", **meta})
    if data["result"] == "confirmed":
        session.root_cause = hyp.cause
        session.state = RcaState.ROOT_CAUSE_FIX
    elif data["result"] == "ruled_out":
        session.check_idx += 1
        session.state = RcaState.CHECKS
        if current_check(session) is None:
            session.state = RcaState.CLOSE  # all hypotheses ruled out, unresolved
    # unclear: the frame didn't answer the check (often the wrong spot);
    # the check stays open for the next dwell. No advancement, no close.
    return rec


def confirm_current(session: RcaSession) -> None:
    """Pinch = technician confirms the current hypothesis by hand."""
    hyp = current_check(session)
    session.checks.append(CheckRecord(hypothesis=hyp.cause, check=hyp.check,
                                      result="manual", evidence="pinch confirm by technician"))
    session.root_cause = hyp.cause
    session.state = RcaState.ROOT_CAUSE_FIX


def parts_for(asset_id: str, root_cause: str | None) -> list[dict]:
    asset = load_assets().get(asset_id, {})
    parts = asset.get("parts", [])
    if not root_cause:
        return parts
    cause = root_cause.lower()
    pick = [p for p in parts if any(w in cause for w in p["part"].lower().split()[:2])]
    return pick or parts


def close_session(session: RcaSession) -> dict:
    session.state = RcaState.CLOSE
    return {
        "asset": session.asset_id, "code": session.code, "symptom": session.symptom_title,
        "root_cause": session.root_cause,
        "checks": [c.__dict__ for c in session.checks],
        "manual": session.manual["title"] if session.manual else None,
        "parts": parts_for(session.asset_id, session.root_cause),
        "frame_jpeg_b64": (base64.b64encode(session.frame_jpeg).decode()
                            if session.frame_jpeg else None),
    }
