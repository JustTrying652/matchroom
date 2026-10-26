"""Export a static, server-less copy of the demo into docs/ (for GitHub Pages).

It replays the cached real-model feeds in data/feeds/ entirely in the browser, so the
hosted demo needs no server and no model calls.

Usage:  python scripts/export_static.py
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from matchroom.agents import PERSONAS  # noqa: E402
from matchroom.api import BRIEF, CACHE_DIR, MATCH, SEED  # noqa: E402
from matchroom.stats import MatchState  # noqa: E402

MODEL = "groq"   # which model's cached feeds to publish


def load_feed(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    recap = raw.pop("__recap__")
    return {"cards": sorted(raw.values(), key=lambda c: c["t"]), "recap": recap}


feeds = {}
for pid in PERSONAS:
    for suffix in ("", "_faults"):
        path = CACHE_DIR / f"{SEED}_{pid}_any_any_{MODEL}{suffix}.json"
        if path.exists():
            feeds[pid + suffix] = load_feed(path)
if not feeds:
    sys.exit(f"No cached '{MODEL}' feeds found in {CACHE_DIR}. Run scripts/prebuild_feeds.py first.")

home, away = (t["code"] for t in MATCH["teams"])
state, snaps, last = MatchState(home, away), {}, -99.0
for i, e in enumerate(MATCH["events"]):
    state.update(e)
    if e["t"] - last >= 15 or e["type"] in ("goal", "period_end"):
        snaps[str(i)], last = state.snapshot(), e["t"]

by_id = {e["id"]: e for e in MATCH["events"]}
needed = {i for f in feeds.values() for c in f["cards"] for i in c["evidence"]}
out = {"meta": MATCH["meta"], "teams": MATCH["teams"],
       "personas": [p for p in PERSONAS if p in feeds], "feeds": feeds,
       "events": [{k: e[k] for k in BRIEF} for e in MATCH["events"]], "snaps": snaps,
       "evidence": {i: by_id[i] for i in needed if i in by_id}}

docs = ROOT / "docs"
(docs / "data").mkdir(parents=True, exist_ok=True)
(docs / "data" / "static.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                                           encoding="utf-8")
shutil.copy(ROOT / "web" / "index.html", docs / "index.html")
size = (docs / "data" / "static.json").stat().st_size // 1024
print(f"Exported {len(feeds)} feeds ({', '.join(feeds)}) to {docs} ({size} KB of data)")