"""FastAPI + WebSocket server pushing cards to the lens simulator."""
from __future__ import annotations
import asyncio
import threading
import time
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

LENS = Path(__file__).resolve().parent.parent / "lens" / "index.html"

app = FastAPI(title="Mr. Jeff Glasses")
app.state.cards: list[dict] = []
app.state.pinches: list[dict] = []
app.state.queues: set[asyncio.Queue] = set()
app.state.next_id = 1


class CardIn(BaseModel):
    title: str
    lines: list = []
    step: Optional[str] = None


class PinchIn(BaseModel):
    card_id: Optional[int] = None


async def _broadcast(msg: dict) -> None:
    for q in list(app.state.queues):
        await q.put(msg)


@app.get("/", response_class=FileResponse)
def lens():
    return FileResponse(LENS)


@app.post("/card")
async def post_card(card: CardIn):
    record = {"id": app.state.next_id, "ts": time.time(), **card.model_dump()}
    app.state.next_id += 1
    app.state.cards.append(record)
    await _broadcast({"type": "card", "card": record})
    return record


@app.get("/history")
def history():
    return {"cards": app.state.cards}


@app.post("/pinch")
def pinch(p: PinchIn):
    record = {"ts": time.time(), "card_id": p.card_id}
    app.state.pinches.append(record)
    return record


@app.get("/pinches")
def pinches():
    return {"pinches": app.state.pinches}


@app.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()
    q: asyncio.Queue = asyncio.Queue()
    app.state.queues.add(q)
    try:
        await ws.send_json({"type": "history", "cards": app.state.cards[-20:]})
        while True:
            await ws.send_json(await q.get())
    except WebSocketDisconnect:
        pass
    finally:
        app.state.queues.discard(q)


def start_in_thread(host: str = "127.0.0.1", port: int = 8000) -> uvicorn.Server:
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    return server


def wait_ready(port: int, timeout: float = 15.0) -> None:
    import requests

    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if requests.get(f"http://127.0.0.1:{port}/history", timeout=1).ok:
                return
        except requests.RequestException:
            time.sleep(0.2)
    raise RuntimeError("server did not start")
