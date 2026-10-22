"""Generate a synthetic match, save it as JSON and print a quick sanity summary.

Usage:  python scripts/generate_match.py --seed 7
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from matchroom.stats import MatchState  # noqa: E402
from matchroom.synthetic.generator import MatchGenerator  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=None, help="output file (default data/synthetic/match_<seed>.json)")
    args = ap.parse_args()

    match = MatchGenerator(args.seed).generate()
    out = Path(args.out) if args.out else ROOT / "data" / "synthetic" / f"match_{args.seed:03d}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(match, indent=1), encoding="utf-8")

    home, away = (t["code"] for t in match["teams"])
    state = MatchState(home, away)
    peak = {"index": 0.0, "clock": ""}
    for e in match["events"]:
        state.update(e)
        mom = state.momentum()
        if abs(mom["index"]) > abs(peak["index"]):
            peak = {"index": mom["index"], "clock": e["clock"]}

    snap = state.snapshot()
    print(f"Saved {len(match['events'])} events to {out}")
    print(f"Final score: {match['meta']['final_score']}")
    for code, s in snap["teams"].items():
        print(f"\n{code}: {s['goals']} goals | {s['shots']} shots ({s['shots_on_target']} on target) | "
              f"xG {s['xg']} | possession {s['possession_pct']}% | pass accuracy {s['pass_accuracy_pct']}%")
        print(f"     tackles won {s['tackles_won']} | pressures {s['pressures']} | "
              f"final-third entries {s['final_third_entries']} | max shot {s['max_shot_kmh']} km/h")
    print(f"\nPeak momentum swing: {peak['index']:+.2f} at {peak['clock']}")


if __name__ == "__main__":
    main()