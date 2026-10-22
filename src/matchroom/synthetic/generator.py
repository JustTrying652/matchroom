"""Synthetic, football-realistic match generator.

Everything here is fictional: clubs, players, venue and scores. Coordinates are
absolute pitch metres (105 x 68). The home team attacks towards x=105, the away
team towards x=0. Each team has hidden strengths plus "spells" (periods of
dominance) so that matches contain real stories: momentum swings, pressure
spells, chaotic phases and controlled phases.
"""
from __future__ import annotations

import math
import random

from ..models import Event, Player, Team

FIRST = ["Amani", "Brian", "Caleb", "Dario", "Emeka", "Farid", "Gideon", "Hamza", "Ivan",
         "Jonas", "Kofi", "Luca", "Mateo", "Nico", "Omar", "Pablo", "Quincy", "Rafael",
         "Samir", "Tomas", "Uriel", "Victor", "Wanjala", "Yusuf", "Zane", "Idris", "Kwame",
         "Leandro", "Mikael", "Nabil"]
LAST = ["Abara", "Brandt", "Castell", "Dube", "Ekwueme", "Fontaine", "Gallo", "Haldane",
        "Ibarra", "Jovanovic", "Kimani", "Lindqvist", "Mbeki", "Novak", "Okafor", "Petrov",
        "Quartey", "Rinaldi", "Sorensen", "Tavares", "Umar", "Vasquez", "Waweru", "Xavier",
        "Yilmaz", "Zielinski", "Achterberg", "Boateng", "Cordero", "Delacroix"]

# (position, shirt number, typical x while attacking)
FORMATION = [("GK", 1, 5), ("RB", 2, 32), ("CB", 5, 26), ("CB", 6, 26), ("LB", 3, 32),
             ("CM", 8, 45), ("CM", 4, 50), ("CM", 10, 45),
             ("RW", 7, 72), ("ST", 9, 82), ("LW", 11, 72)]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def build_team(rng, code, name, color, used, attack, control, press, finishing) -> Team:
    players = []
    for pos, number, base_x in FORMATION:
        while True:
            full = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if full not in used:
                used.add(full)
                break
        players.append(Player(f"{code}{number:02d}", full, number, pos, float(base_x)))
    return Team(code, name, color, attack, control, press, finishing, players)


class MatchGenerator:
    def __init__(self, seed: int = 7):
        self.seed = seed
        self.rng = random.Random(seed)
        r = self.rng
        used: set[str] = set()
        self.teams = [
            build_team(r, "LKU", "Lakeshore United", "#1f77b4", used,
                       r.uniform(.52, .70), r.uniform(.50, .72), r.uniform(.45, .70), r.uniform(.45, .70)),
            build_team(r, "SRC", "Sunridge City", "#e4572e", used,
                       r.uniform(.52, .70), r.uniform(.50, .72), r.uniform(.45, .70), r.uniform(.45, .70)),
        ]
        self.score = [0, 0]
        self.events: list[Event] = []
        self.t = 0.0
        self.period = 1
        self.stop1 = r.randint(60, 180)
        self.stop2 = r.randint(150, 300)
        self.poss = 0
        self.ball = (52.5, 34.0)       # in the frame of the team in possession
        self.carrier: Player | None = None
        self.carded: set[str] = set()
        first, second = r.sample([0, 1], 2)
        self.spells = [  # (team index, centre minute, width, amplitude)
            (first, r.uniform(12, 30), r.uniform(5, 8), r.uniform(.25, .40)),
            (second, r.uniform(55, 75), r.uniform(5, 9), r.uniform(.25, .45)),
            (first, r.uniform(78, 88), 4.0, 0.30),
        ]

    # ------------------------------------------------------------ helpers
    def _game_minutes(self) -> float:
        gt = self.t if self.period == 1 else self.t - self.stop1
        return gt / 60.0

    def _spell(self, idx: int) -> float:
        m = self._game_minutes()
        s = sum(a * math.exp(-(((m - c) / w) ** 2)) for tm, c, w, a in self.spells if tm == idx)
        return min(0.55, s)

    def _clock(self) -> tuple[int, str]:
        gt = self.t if self.period == 1 else self.t - self.stop1
        limit = 2700 if self.period == 1 else 5400
        if gt >= limit:
            return limit // 60, f"{limit // 60}+{int((gt - limit) // 60) + 1}'"
        minute = int(gt // 60) + 1
        return minute, f"{minute}'"

    @staticmethod
    def _abs(idx: int, x: float, y: float) -> tuple[float, float]:
        return (round(x, 1), round(y, 1)) if idx == 0 else (round(105 - x, 1), round(68 - y, 1))

    def _pick(self, idx, x, forwards=False, exclude=None, allow_gk=False) -> Player:
        pool = [p for p in self.teams[idx].players
                if (allow_gk or p.position != "GK") and p.id != exclude]
        w = [math.exp(-(((p.base_x - x) / 22.0) ** 2)) * (3.0 if forwards and p.base_x > 60 else 1.0)
             for p in pool]
        return self.rng.choices(pool, weights=w, k=1)[0]

    def _emit(self, typ, idx, pos, player=None, end=None, outcome=None, recipient=None,
              metrics=None, poss_idx=None):
        minute, clock = self._clock()
        x, y = self._abs(idx, *pos)
        ex = ey = None
        if end is not None:
            ex, ey = self._abs(idx, *end)
        pi = self.poss if poss_idx is None else poss_idx
        self.events.append(Event(
            id=f"e{len(self.events) + 1:04d}", t=round(self.t, 1), minute=minute, clock=clock,
            period=self.period, type=typ, team=self.teams[idx].code, poss=self.teams[pi].code,
            player_id=player.id if player else None, player=player.name if player else None,
            x=x, y=y, end_x=ex, end_y=ey, outcome=outcome,
            recipient_id=recipient.id if recipient else None,
            recipient=recipient.name if recipient else None,
            metrics=metrics or {}))

    def _turnover(self, reason: str, new_ball: tuple[float, float], carrier: Player | None = None):
        self.poss = 1 - self.poss
        self.ball = new_ball
        self.carrier = carrier
        self._emit("possession_change", self.poss, new_ball, carrier, outcome=reason)

    # ------------------------------------------------------------ actions
    def _step(self):
        r = self.rng
        atk_i = self.poss
        dfn_i = 1 - atk_i
        atk, dfn = self.teams[atk_i], self.teams[dfn_i]
        s_atk, s_dfn = self._spell(atk_i), self._spell(dfn_i)
        pressure = _clamp(0.2 + 0.4 * dfn.press + 0.8 * s_dfn - 0.3 * s_atk, 0.05, 0.95)
        self.t += r.uniform(2.5, 8.0)
        x, y = self.ball

        if pressure > 0.4 and r.random() < pressure * 0.35:
            d = self._pick(dfn_i, 105 - x)
            self._emit("pressure", dfn_i, (105 - x, 68 - y), d, outcome="applied",
                       recipient=self.carrier, metrics={"intensity": round(pressure, 2)})

        p_shot = 0.0 if x < 72 else 0.02 + 0.10 * (x - 72) / 33 + 0.08 * s_atk
        p_tackle = 0.05 + 0.05 * dfn.press + 0.05 * s_dfn
        roll = r.random()
        if roll < p_shot:
            self._shot(atk_i, pressure)
        elif roll < p_shot + p_tackle:
            self._tackle(atk_i, pressure)
        elif r.random() < 0.012:
            self._foul(atk_i)
        else:
            self._pass(atk_i, pressure, s_atk)

    def _pass(self, atk_i, pressure, s_atk):
        r = self.rng
        atk = self.teams[atk_i]
        x, y = self.ball
        passer = self.carrier or self._pick(atk_i, x)
        forward_p = min(0.85, 0.45 + 0.30 * atk.attack + 0.40 * s_atk)
        dist = r.uniform(6, 36)
        ang = r.gauss(0, 0.7) if r.random() < forward_p else r.choice([-1, 1]) * r.uniform(1.4, 3.0)
        ex = _clamp(x + dist * math.cos(ang), 1.0, 104.0)
        ey = _clamp(y + dist * math.sin(ang), 1.0, 67.0)
        length = math.hypot(ex - x, ey - y)
        progress = ex - x
        difficulty = _clamp(0.05 + length / 110 + max(progress, 0) / 140 + pressure * 0.25
                            + (0.08 if ex > 88 else 0.0), 0.02, 0.98)
        p_ok = _clamp(0.98 - 0.45 * difficulty + 0.15 * (atk.control + s_atk - 0.6), 0.2, 0.97)
        metrics = {"distance_m": round(length, 1), "difficulty": round(difficulty, 2),
                   "progress_m": round(progress, 1),
                   "ball_speed_kmh": round(_clamp(28 + length * 1.1 + r.gauss(0, 4), 20, 95), 1),
                   "pressure": round(pressure, 2)}
        if r.random() < p_ok:
            rec = self._pick(atk_i, ex, exclude=passer.id)
            self._emit("pass", atk_i, (x, y), passer, end=(ex, ey), outcome="complete",
                       recipient=rec, metrics=metrics)
            self.ball, self.carrier = (ex, ey), rec
            if progress > 18 and pressure < 0.5 and r.random() < 0.15:
                self._emit("sprint", atk_i, (ex, ey), rec, outcome="threshold_triggered",
                           metrics={"speed_kmh": round(r.uniform(29, 35.5), 1),
                                    "distance_m": round(r.uniform(18, 45), 1),
                                    "trigger": "speed>=29km/h and distance>=18m"})
            return
        self._emit("pass", atk_i, (x, y), passer, end=(ex, ey), outcome="incomplete", metrics=metrics)
        tx, ty = 105 - ex, 68 - ey
        if r.random() < 0.55:
            d = self._pick(1 - atk_i, tx)
            self._emit("interception", 1 - atk_i, (tx, ty), d, outcome="won")
            self._turnover("interception", (tx, ty), d)
        else:
            self._turnover("out_of_play", (tx, ty))

    def _tackle(self, atk_i, pressure):
        r = self.rng
        dfn_i = 1 - atk_i
        dfn = self.teams[dfn_i]
        x, y = self.ball
        pos = (105 - x, 68 - y)
        d = self._pick(dfn_i, pos[0])
        win = r.random() < 0.42 + 0.30 * (dfn.press - 0.5) + 0.20 * pressure
        self._emit("tackle", dfn_i, pos, d, outcome="won" if win else "lost",
                   recipient=self.carrier, metrics={"pressure": round(pressure, 2)})
        if win:
            self._turnover("tackle", pos, d)

    def _foul(self, atk_i):
        r = self.rng
        dfn_i = 1 - atk_i
        x, y = self.ball
        pos = (105 - x, 68 - y)
        d = self._pick(dfn_i, pos[0])
        self._emit("foul", dfn_i, pos, d, outcome="conceded", recipient=self.carrier)
        if r.random() < 0.15 and d.id not in self.carded:
            self.carded.add(d.id)
            self._emit("card", dfn_i, pos, d, outcome="yellow")
        self.t += r.uniform(8, 20)

    def _shot(self, atk_i, pressure, from_set_piece=False):
        r = self.rng
        atk = self.teams[atk_i]
        x, y = self.ball
        shooter = self._pick(atk_i, x, forwards=True)
        dist = math.hypot(105 - x, 34 - y)
        xg = _clamp(0.015 + 0.55 * math.exp(-dist / 11) * (1 - 0.5 * pressure), 0.01, 0.76)
        p_goal = min(0.9, xg * (0.65 + 0.70 * atk.finishing))
        if r.random() < p_goal:
            outcome = "goal"
        else:
            v = r.random()
            outcome = "saved" if v < 0.38 else ("blocked" if v < 0.62 else "off_target")
        self._emit("shot", atk_i, (x, y), shooter, end=(105.0, 34 + r.uniform(-3.5, 3.5)),
                   outcome=outcome,
                   metrics={"xg": round(xg, 3), "distance_m": round(dist, 1),
                            "shot_speed_kmh": round(_clamp(r.gauss(95, 12), 60, 135), 1),
                            "pressure": round(pressure, 2), "set_piece": from_set_piece})
        dfn_i = 1 - atk_i
        gk = self.teams[dfn_i].players[0]
        if outcome == "goal":
            self.score[atk_i] += 1
            self._emit("goal", atk_i, (x, y), shooter, outcome="goal",
                       metrics={"score": f"{self.score[0]}-{self.score[1]}", "xg": round(xg, 3)})
            self.t += r.uniform(30, 50)
            self.poss, self.ball, self.carrier = dfn_i, (52.5, 34.0), None
            self._emit("possession_change", dfn_i, self.ball, outcome="kickoff")
        elif outcome == "saved":
            self._emit("save", dfn_i, (3.0, 34 + r.uniform(-4, 4)), gk, outcome="saved")
            if not from_set_piece and r.random() < 0.35:
                self._corner(atk_i, pressure)
            else:
                self._turnover("save", (6.0, 34.0), gk)
        elif outcome == "blocked":
            if not from_set_piece and r.random() < 0.30:
                self._corner(atk_i, pressure)
            else:
                self._turnover("blocked", (r.uniform(12, 30), r.uniform(15, 53)))
        else:
            self._turnover("goal_kick", (6.0, 34.0), gk)

    def _corner(self, atk_i, pressure):
        r = self.rng
        self.t += r.uniform(8, 15)
        self._emit("corner", atk_i, (104.0, r.choice([1.0, 67.0])), outcome="awarded")
        if r.random() < 0.30:
            self.ball = (97.0, 34 + r.uniform(-8, 8))
            self._shot(atk_i, min(0.95, pressure + 0.15), from_set_piece=True)
        else:
            self._turnover("clearance", (r.uniform(25, 45), r.uniform(10, 58)))

    # ------------------------------------------------------------ driver
    def run(self):
        self._emit("period_start", 0, (52.5, 34.0), outcome="1")
        end1 = 2700 + self.stop1
        while self.t < end1:
            self._step()
        self._emit("period_end", self.poss, self.ball, outcome="1")
        self.period = 2
        self.t = max(self.t, end1)
        self.poss, self.ball, self.carrier = 1, (52.5, 34.0), None
        self._emit("period_start", 1, (52.5, 34.0), outcome="2")
        end2 = 5400 + self.stop1 + self.stop2
        while self.t < end2:
            self._step()
        self._emit("period_end", self.poss, self.ball, outcome="2")

    def generate(self) -> dict:
        self.run()
        return {
            "meta": {
                "match_id": f"SYN-{self.seed:04d}",
                "competition": "Synthetic League (fictional)",
                "venue": "Riverside Park (fictional)",
                "seed": self.seed,
                "final_score": {self.teams[0].code: self.score[0], self.teams[1].code: self.score[1]},
                "disclaimer": "Synthetic data. All clubs, players and results are fictional.",
            },
            "teams": [t.to_dict() for t in self.teams],
            "events": [e.to_dict() for e in self.events],
        }