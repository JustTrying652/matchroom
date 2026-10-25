"""Pre-generate and cache the feed for every standard fan view.

The hosted demo then replays these files and needs no model calls. Run it once with your
model configured (Azure or GitHub Models), then commit the new files in data/feeds/.

Usage:  python scripts/prebuild_feeds.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from matchroom.agents import PERSONAS  # noqa: E402
from matchroom.api import CACHE_DIR, MATCH, SEED, _slug  # noqa: E402
from matchroom.llm import get_llm  # noqa: E402
from matchroom.pipeline import MatchDesk  # noqa: E402


def build(persona, faults: bool) -> None:
    llm = get_llm()
    key = f"{SEED}_{persona.id}_{_slug(None)}_{_slug(None)}_{llm.name}{'_faults' if faults else ''}"
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        print("skip (already built):", path.name)
        return
    desk = MatchDesk(MATCH, llm, inject_faults=faults)
    cache: dict = {}
    for e in MATCH["events"]:
        desk.process_event(e, persona, cache)
    desk.recap(persona, cache)
    fallbacks = sum(1 for v in cache.values() if v["verification"]["source"] == "template-fallback")
    if fallbacks:
        print(f"NOT saved: {key} ({fallbacks} cards fell back to templates; check the model and retry)")
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    print(f"saved {path.name} ({len(cache) - 1} cards + recap, model: {llm.name})")


if __name__ == "__main__":
    for p in PERSONAS.values():
        build(p, faults=False)
        if p.id in ("casual_en", "analyst_en"):
            build(p, faults=True)