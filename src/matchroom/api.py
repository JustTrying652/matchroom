"""FastAPI app: live match replay over Server-Sent Events, plus the web UI.

Run:  python -m uvicorn matchroom.api:app --app-dir src --port 8000
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .agents import PERSONAS, Persona
from .llm import get_llm
from .pipeline import MatchDesk
from .synthetic.generator import MatchGenerator

ROOT = Path(__file__).resolve().parents[2]
SEED = int(os.environ.get("MATCHROOM_SEED", "65"))
DATA_FILE = ROOT / "data" / "synthetic" / f"match_{SEED:03d}.json"
CACHE_DIR = ROOT / "data" / "feeds"      # finished feeds are cached so judges don't spend model calls
WEB_DIR = ROOT / "web"

MATCH = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() \
    else MatchGenerator(SEED).generate()
EVENTS = {e["id"]: e for e in MATCH["events"]}
BRIEF = ("id", "t", "clock", "type", "team", "player", "x", "y", "end_x", "end_y", "outcome")

app = FastAPI(title="Matchroom")


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _slug(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "any").lower())


@app.get("/api/match")
def match_info():
    return {"meta": MATCH["meta"], "teams": MATCH["teams"], "personas": list(PERSONAS)}


@app.get("/api/evidence")
def evidence(ids: str):
    return {"events": [EVENTS[i] for i in ids.split(",") if i in EVENTS]}


@app.get("/api/health")
def health():
    return {"ok": True, "model": get_llm().name, "events": len(EVENTS)}


@app.get("/api/stream")
async def stream(persona: str = "casual_en", fav: str = "", player: str = "",
                 speed: float = Query(60, ge=1, le=5000), faults: bool = False):
    if persona not in PERSONAS:
        raise HTTPException(400, "unknown persona")
    base = PERSONAS[persona]
    p = Persona(base.id, base.language, base.depth, fav or None, player or None)
    llm = get_llm()
    desk = MatchDesk(MATCH, llm, inject_faults=faults)
    base = f"{SEED}_{p.id}_{_slug(fav)}_{_slug(player)}"
    suffix = "_faults" if faults else ""
    found = next((f for n in (llm.name, "azure-openai", "groq")
                  if (f := CACHE_DIR / f"{base}_{n}{suffix}.json").exists()), None)
    path = found or CACHE_DIR / f"{base}_{llm.name}{suffix}.json"
    fresh = found is None
    cache: dict = {} if fresh else json.loads(found.read_text(encoding="utf-8"))

    async def gen():
        prev_t, last_snap = 0.0, -99.0
        for e in MATCH["events"]:
            cards = await asyncio.to_thread(desk.process_event, e, p, cache)
            snap = None
            if e["t"] - last_snap >= 15 or cards:
                snap, last_snap = desk.detector.state.snapshot(), e["t"]
            yield _sse({"kind": "event", "e": {k: e[k] for k in BRIEF}, "snap": snap})
            for c in cards:
                yield _sse({"kind": "card", "card": c})
            await asyncio.sleep(min(0.6, max(0.0, (e["t"] - prev_t) / speed)))
            prev_t = e["t"]
        recap = await asyncio.to_thread(desk.recap, p, cache)
        yield _sse({"kind": "recap", "recap": recap})
        yield _sse({"kind": "end"})
        if fresh:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")