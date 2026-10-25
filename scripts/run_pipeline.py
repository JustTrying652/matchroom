"""Run the full multi-agent pipeline over a generated match and print the feed.

Usage:
  python scripts/run_pipeline.py --seed 65 --persona casual_en
  python scripts/run_pipeline.py --seed 65 --persona analyst_sw --faults
Options: --faults makes the offline model write wrong facts on the first goal draft,
so you can watch the Verifier reject it and the Narrator recover.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from matchroom.agents import PERSONAS, Persona  # noqa: E402
from matchroom.llm import get_llm  # noqa: E402
from matchroom.pipeline import MatchDesk  # noqa: E402
from matchroom.synthetic.generator import MatchGenerator  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=65)
    ap.add_argument("--persona", default="casual_en", choices=list(PERSONAS))
    ap.add_argument("--faults", action="store_true")
    ap.add_argument("--fav", default=None, help="favourite club code, e.g. LKU")
    ap.add_argument("--player", default=None, help="focus on one player (full name)")
    ap.add_argument("--json", default=None, help="also write the feed to this JSON file")
    args = ap.parse_args()

    path = ROOT / "data" / "synthetic" / f"match_{args.seed:03d}.json"
    match = json.loads(path.read_text()) if path.exists() else MatchGenerator(args.seed).generate()
    base = PERSONAS[args.persona]
    persona = Persona(base.id, base.language, base.depth, args.fav, args.player)

    llm = get_llm()
    desk = MatchDesk(match, llm, inject_faults=args.faults)
    feed = desk.run(persona)

    print(f"Model: {llm.name} | persona: {persona.id} | cards: {len(feed['cards'])}\n")
    for c in feed["cards"]:
        v = c["verification"]
        flag = "" if v["attempts"] == 1 and v["verified"] else f"   [attempts {v['attempts']}, verified={v['verified']}]"
        print(f"{c['clock']:>6}  {c['type']:<15} {c['text']}{flag}")
        for r in v["rejections"]:
            print(f"        x rejected attempt {r['attempt']}: {'; '.join(r['issues'])}")
        print(f"        evidence: {', '.join(c['evidence'])}")
    print(f"\nRECAP: {feed['recap']['text']}")
    if args.json:
        Path(args.json).write_text(json.dumps(feed, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()