"""Interpret stage: turns the raw event stream into live football state.

MatchState is fed one event at a time (exactly as a live feed would) and can
produce a snapshot at any moment: score, team stats, a rolling momentum index
and a control-vs-chaos reading.
"""
from __future__ import annotations

from collections import defaultdict, deque

MOMENTUM_WINDOW = 300.0   # seconds
CHAOS_WINDOW = 180.0      # seconds


class MatchState:
    def __init__(self, home: str, away: str):
        self.home, self.away = home, away
        self.codes = (home, away)
        self.team = {c: defaultdict(float) for c in self.codes}
        self.player = defaultdict(lambda: defaultdict(float))
        self.score = {home: 0, away: 0}
        self.poss_time = {home: 0.0, away: 0.0}
        self.last_t = 0.0
        self.last_poss: str | None = None
        self.clock = "0'"
        self._momentum = deque()   # (t, team, weight)
        self._turnovers = deque()  # t
        self._passes = deque()     # t

    # ---------------------------------------------------------------- feed
    def update(self, e: dict) -> None:
        t, typ, team, m = e["t"], e["type"], e["team"], e.get("metrics", {})
        if self.last_poss is not None:
            self.poss_time[self.last_poss] += max(0.0, t - self.last_t)
        self.last_t, self.last_poss, self.clock = t, e["poss"], e["clock"]
        s = self.team.get(team)
        pl = self.player[e["player_id"]] if e.get("player_id") else None
        if s is None:
            return

        if typ == "pass":
            s["passes"] += 1
            s["difficulty_sum"] += m.get("difficulty", 0)
            self._passes.append(t)
            if pl is not None:
                pl["passes"] += 1
            if e["outcome"] == "complete":
                s["passes_ok"] += 1
                if pl is not None:
                    pl["passes_ok"] += 1
                if m.get("progress_m", 0) > 15:
                    s["progressive_passes"] += 1
                    self._momentum.append((t, team, 0.2))
                if self._in_final_third(team, e["end_x"]) and not self._in_final_third(team, e["x"]):
                    s["final_third_entries"] += 1
                    self._momentum.append((t, team, 0.4))
        elif typ == "shot":
            s["shots"] += 1
            s["xg"] += m.get("xg", 0)
            s["max_shot_kmh"] = max(s["max_shot_kmh"], m.get("shot_speed_kmh", 0))
            if e["outcome"] in ("saved", "goal"):
                s["shots_on_target"] += 1
            if pl is not None:
                pl["shots"] += 1
                pl["xg"] += m.get("xg", 0)
            self._momentum.append((t, team, 0.5 + 3.0 * m.get("xg", 0)))
        elif typ == "goal":
            s["goals"] += 1
            self.score[team] += 1
            if pl is not None:
                pl["goals"] += 1
            self._momentum.append((t, team, 2.0))
        elif typ == "tackle":
            s["tackles"] += 1
            if e["outcome"] == "won":
                s["tackles_won"] += 1
        elif typ == "interception":
            s["interceptions"] += 1
        elif typ == "foul":
            s["fouls"] += 1
        elif typ == "card":
            s["cards"] += 1
        elif typ == "corner":
            s["corners"] += 1
            self._momentum.append((t, team, 0.8))
        elif typ == "pressure":
            s["pressures"] += 1
            self._momentum.append((t, team, 0.15))
        elif typ == "sprint":
            s["sprints"] += 1
        elif typ == "possession_change":
            self._turnovers.append(t)

    def _in_final_third(self, team: str, x: float | None) -> bool:
        if x is None:
            return False
        return x >= 70 if team == self.home else x <= 35

    def _prune(self) -> None:
        now = self.last_t
        while self._momentum and now - self._momentum[0][0] > MOMENTUM_WINDOW:
            self._momentum.popleft()
        while self._turnovers and now - self._turnovers[0] > CHAOS_WINDOW:
            self._turnovers.popleft()
        while self._passes and now - self._passes[0] > CHAOS_WINDOW:
            self._passes.popleft()

    # ------------------------------------------------------------ outputs
    def momentum(self) -> dict:
        """Index from -1 (away dominant) to +1 (home dominant) over the last 5 minutes."""
        self._prune()
        w = {c: 0.0 for c in self.codes}
        for _, team, weight in self._momentum:
            w[team] += weight
        total = w[self.home] + w[self.away]
        index = (w[self.home] - w[self.away]) / total if total > 1.0 else 0.0
        leader = self.home if index > 0.25 else self.away if index < -0.25 else None
        return {"index": round(index, 2), "leader": leader,
                "home_pressure": round(w[self.home], 1), "away_pressure": round(w[self.away], 1)}

    def control_vs_chaos(self) -> dict:
        """Chaos = how often the ball changes hands; rhythm = passes per minute."""
        self._prune()
        turnovers_per_min = len(self._turnovers) / (CHAOS_WINDOW / 60)
        passes_per_min = len(self._passes) / (CHAOS_WINDOW / 60)
        chaos = min(1.0, turnovers_per_min / 4.0)
        label = "controlled" if chaos < 0.45 else "balanced" if chaos < 0.7 else "chaotic"
        tempo = "high tempo" if passes_per_min > 14 else "steady" if passes_per_min > 9 else "slow build-up"
        return {"chaos_index": round(chaos, 2), "label": label,
                "turnovers_per_min": round(turnovers_per_min, 1),
                "passes_per_min": round(passes_per_min, 1), "rhythm": tempo}

    def snapshot(self) -> dict:
        total_poss = sum(self.poss_time.values()) or 1.0
        teams = {}
        for c in self.codes:
            s = self.team[c]
            att = s["passes"] or 1.0
            teams[c] = {
                "goals": int(s["goals"]), "shots": int(s["shots"]),
                "shots_on_target": int(s["shots_on_target"]), "xg": round(s["xg"], 2),
                "possession_pct": round(100 * self.poss_time[c] / total_poss),
                "passes": int(s["passes"]),
                "pass_accuracy_pct": round(100 * s["passes_ok"] / att),
                "avg_pass_difficulty": round(s["difficulty_sum"] / att, 2),
                "progressive_passes": int(s["progressive_passes"]),
                "final_third_entries": int(s["final_third_entries"]),
                "tackles_won": int(s["tackles_won"]), "interceptions": int(s["interceptions"]),
                "pressures": int(s["pressures"]), "fouls": int(s["fouls"]),
                "corners": int(s["corners"]), "cards": int(s["cards"]),
                "sprints": int(s["sprints"]), "max_shot_kmh": round(s["max_shot_kmh"], 1),
            }
        return {"clock": self.clock, "t": self.last_t, "score": dict(self.score),
                "teams": teams, "momentum": self.momentum(),
                "control_vs_chaos": self.control_vs_chaos()}