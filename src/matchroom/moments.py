"""Explain stage, part 1: spot the moments worth talking about.

MomentDetector is fed one event at a time (like a live feed). Every moment
carries the ids of the events that prove it, so each statement made later can
be traced back to the raw data.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, field

from .stats import MatchState


@dataclass
class Moment:
    id: str
    t: float
    clock: str
    type: str
    importance: float
    team: str | None
    player: str | None
    facts: dict = field(default_factory=dict)
    evidence: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class MomentDetector:
    def __init__(self, home: str, away: str, names: dict[str, str]):
        self.home, self.away, self.names = home, away, names
        self.state = MatchState(home, away)
        self.recent: deque = deque()      # events from the last 5 minutes
        self.moments: list[Moment] = []
        self._goals: dict = defaultdict(int)
        self._cool: dict = {}
        self._leader = None
        self._label = None

    # ------------------------------------------------------------------ feed
    def feed(self, e: dict) -> list[Moment]:
        self.state.update(e)
        self.recent.append(e)
        while e["t"] - self.recent[0]["t"] > 300:
            self.recent.popleft()
        before = len(self.moments)
        typ = e["type"]
        if typ == "goal":
            self._goal(e)
        elif typ == "shot" and e["outcome"] != "goal" and e["metrics"].get("xg", 0) >= 0.22:
            self._big_chance(e)
        elif typ == "card":
            self._card(e)
        elif typ == "sprint" and e["metrics"]["speed_kmh"] >= 33:
            self._sprint(e)
        elif typ == "period_end":
            self._period_end(e)
        self._phases(e)
        return self.moments[before:]

    # --------------------------------------------------------------- helpers
    def _mk(self, e, typ, importance, team=None, player=None, facts=None, evidence=None) -> Moment:
        m = Moment(f"m{len(self.moments) + 1:03d}", e["t"], e["clock"], typ,
                   round(min(1.0, importance), 2), team, player, facts or {}, evidence or [e["id"]])
        self.moments.append(m)
        return m

    def _ok(self, key: str, t: float, gap: float) -> bool:
        if t < self._cool.get(key, 0):
            return False
        self._cool[key] = t + gap
        return True

    def _last(self, pred, e, within=None):
        for x in reversed(self.recent):
            if within is not None and e["t"] - x["t"] > within:
                return None
            if pred(x):
                return x
        return None

    # ---------------------------------------------------------------- rules
    def _goal(self, e):
        team = e["team"]
        opp = self.away if team == self.home else self.home
        sf, sa = self.state.score[team], self.state.score[opp]
        shot = self._last(lambda x: x["type"] == "shot" and x["team"] == team
                          and x["player_id"] == e["player_id"], e)
        assist = self._last(lambda x: x["type"] == "pass" and x["outcome"] == "complete"
                            and x["team"] == team and x.get("recipient_id") == e["player_id"], e, 20)
        if sf + sa == 1:
            ctx = "opening goal"
        elif sf == sa:
            ctx = "equaliser"
        elif sf - 1 == sa:
            ctx = "takes the lead"
        elif sf < sa:
            ctx = "pulls one back"
        else:
            ctx = "extends the lead"
        self._goals[e["player_id"]] += 1
        h, a = self.state.score[self.home], self.state.score[self.away]
        sm = shot["metrics"] if shot else {}
        facts = {"scorer": e["player"], "team": self.names[team], "clock": e["clock"],
                 "minute": e["minute"], "score": f"{h}-{a}", "context": ctx,
                 "xg": round(e["metrics"]["xg"], 2), "shot_speed_kmh": sm.get("shot_speed_kmh"),
                 "distance_m": sm.get("distance_m"), "assist": assist["player"] if assist else None,
                 "goals_in_match": self._goals[e["player_id"]]}
        evidence = [x["id"] for x in (assist, shot) if x] + [e["id"]]
        imp = 0.9 + (0.05 if ctx in ("equaliser", "takes the lead") else 0) \
            + (0.05 if self._goals[e["player_id"]] > 1 else 0)
        self._mk(e, "goal", imp, team, e["player"], facts, evidence)

    def _big_chance(self, e):
        m = e["metrics"]
        facts = {"player": e["player"], "team": self.names[e["team"]], "clock": e["clock"],
                 "minute": e["minute"], "xg": round(m["xg"], 2), "outcome": e["outcome"].replace("_", " "),
                 "shot_speed_kmh": m["shot_speed_kmh"], "distance_m": m["distance_m"]}
        self._mk(e, "big_chance", min(0.8, 0.55 + 0.4 * m["xg"]), e["team"], e["player"], facts)

    def _card(self, e):
        foul = self._last(lambda x: x["type"] == "foul" and x["team"] == e["team"], e, 15)
        facts = {"player": e["player"], "team": self.names[e["team"]], "clock": e["clock"],
                 "minute": e["minute"], "card": "yellow card"}
        self._mk(e, "card", 0.5, e["team"], e["player"], facts, [x["id"] for x in (foul, e) if x])

    def _sprint(self, e):
        m = e["metrics"]
        facts = {"player": e["player"], "team": self.names[e["team"]], "clock": e["clock"],
                 "minute": e["minute"], "speed_kmh": m["speed_kmh"], "distance_m": m["distance_m"],
                 "trigger": m["trigger"]}
        self._mk(e, "sprint", 0.3, e["team"], e["player"], facts)

    def _period_end(self, e):
        s = self.state.snapshot()
        h, a = self.home, self.away
        facts = {"clock": e["clock"], "minute": e["minute"],
                 "score": f"{s['score'][h]}-{s['score'][a]}",
                 "score_line": f"{self.names[h]} {s['score'][h]}-{s['score'][a]} {self.names[a]}",
                 "home": self.names[h], "away": self.names[a],
                 "home_shots": s["teams"][h]["shots"], "away_shots": s["teams"][a]["shots"],
                 "home_xg": s["teams"][h]["xg"], "away_xg": s["teams"][a]["xg"],
                 "home_possession_pct": s["teams"][h]["possession_pct"],
                 "away_possession_pct": s["teams"][a]["possession_pct"]}
        self._mk(e, "half_time" if e["period"] == 1 else "full_time",
                 0.7 if e["period"] == 1 else 0.8, None, None, facts)

    def _phases(self, e):
        t = e["t"]
        if t < 420:
            return
        mom = self.state.momentum()
        leader = mom["leader"]
        if leader != self._leader:
            self._leader = leader
            mine = [x for x in self.recent if x["team"] == leader
                    and x["type"] in ("shot", "corner", "goal")] if leader else []
            shots = [x for x in mine if x["type"] == "shot"]
            corners = [x for x in mine if x["type"] == "corner"]
            if len(shots) + len(corners) >= 3 and self._ok("momentum", t, 420):
                facts = {"team": self.names[leader], "clock": e["clock"], "minute": e["minute"],
                         "momentum_index": mom["index"], "shots_5min": len(shots),
                         "xg_5min": round(sum(x["metrics"]["xg"] for x in shots), 2),
                         "corners_5min": len(corners)}
                self._mk(e, "momentum_swing", 0.5 + 0.35 * abs(mom["index"]), leader, None, facts,
                         [x["id"] for x in mine[-6:]])
        cvc = self.state.control_vs_chaos()
        label = cvc["label"]
        if label != self._label:
            self._label = label
            if label == "chaotic" and self._ok("chaos", t, 900):
                turns = [x["id"] for x in self.recent
                         if x["type"] == "possession_change" and t - x["t"] <= 180]
                facts = {"clock": e["clock"], "minute": e["minute"], "label": label,
                         "turnovers_per_min": cvc["turnovers_per_min"],
                         "passes_per_min": cvc["passes_per_min"], "rhythm": cvc["rhythm"]}
                self._mk(e, "chaos_phase", 0.45, None, None, facts, turns[-6:] or [e["id"]])
            elif label == "controlled" and self._ok("control", t, 900):
                cnt = Counter(x["poss"] for x in self.recent if t - x["t"] <= 180)
                if cnt:
                    team = cnt.most_common(1)[0][0]
                    passes = [x["id"] for x in self.recent if x["type"] == "pass"
                              and x["team"] == team and x["outcome"] == "complete"]
                    facts = {"team": self.names[team], "clock": e["clock"], "minute": e["minute"],
                             "label": label, "share_pct": round(100 * cnt[team] / sum(cnt.values())),
                             "passes_per_min": cvc["passes_per_min"]}
                    self._mk(e, "control_phase", 0.4, team, None, facts, passes[-6:] or [e["id"]])