"""The match desk: wires the five stages together.

Ingest -> Interpret (stats) -> Explain (moments + Analyst) -> Write (Narrator <-> Verifier)
-> Render (overlay cards) -> Personalize (per-fan persona).
"""
from __future__ import annotations

from .agents import (Analyst, Narrator, Persona, Personalizer, RecapWriter, Verifier)
from .llm import MockLLM, get_llm
from .moments import MomentDetector

def _tamper(draft: dict) -> dict:
    """Demo mode: simulate a model hallucination by adding an invented statistic."""
    return {**draft, "text": draft.get("text", "") + " It was his 97th goal of the season."}

LAYER = {"goal": "goal_banner", "big_chance": "lower_third", "card": "lower_third",
         "sprint": "player_tag", "momentum_swing": "stat_card", "chaos_phase": "stat_card",
         "control_phase": "stat_card", "half_time": "scoreboard", "full_time": "scoreboard"}
TITLE = {
    "en": {"goal": "GOAL", "big_chance": "BIG CHANCE", "card": "YELLOW CARD", "sprint": "SPEED",
           "momentum_swing": "MOMENTUM", "chaos_phase": "CHAOS", "control_phase": "CONTROL",
           "half_time": "HALF TIME", "full_time": "FULL TIME"},
    "sw": {"goal": "MAGOLI", "big_chance": "NAFASI KUBWA", "card": "KADI YA NJANO", "sprint": "KASI",
           "momentum_swing": "KASI YA MCHEZO", "chaos_phase": "VURUGU", "control_phase": "UDHIBITI",
           "half_time": "MAPUMZIKO", "full_time": "MWISHO WA MCHEZO"},
}


class MatchDesk:
    def __init__(self, match: dict, llm=None, max_attempts: int = 3, inject_faults: bool = False):
        self.match = match
        teams = match["teams"]
        self.home, self.away = teams[0]["code"], teams[1]["code"]
        self.names = {t["code"]: t["name"] for t in teams}
        self.colors = {t["code"]: t["color"] for t in teams}
        roster = {p["name"] for t in teams for p in t["players"]}
        self.inject_faults = inject_faults
        self.llm = llm or get_llm()
        self.max_attempts = max_attempts
        self.detector = MomentDetector(self.home, self.away, self.names)
        self.analyst = Analyst(self.names)
        self.narrator = Narrator(self.llm)
        self.recapper = RecapWriter(self.llm)
        self.verifier = Verifier(roster)
        self.personalizer = Personalizer()
        self._safe = MockLLM()   # deterministic fallback if the model keeps failing verification

    # ------------------------------------------------------------- live feed
    def process_event(self, e: dict, persona: Persona, cache: dict | None = None) -> list[dict]:
        cards = []
        for moment in self.detector.feed(e):
            m = moment.to_dict()
            if not self.personalizer.wants(m, persona):
                continue
            card = cache.get(m["id"]) if cache is not None else None
            if card is None:
                card = self._card(m, persona)
                if cache is not None:
                    cache[m["id"]] = card
            cards.append(card)
        return cards

    def run(self, persona: Persona) -> dict:
        cards = []
        for e in self.match["events"]:
            cards += self.process_event(e, persona)
        return {"persona": persona.id, "cards": cards, "recap": self.recap(persona)}

    # ------------------------------------------------------------- internals
    def _loop(self, write, fallback, facts):
        rejections, feedback = [], []
        for attempt in range(self.max_attempts):
            draft = write(attempt, feedback)
            issues = self.verifier.check(draft, facts)
            if not issues:
                return draft, {"verified": True, "attempts": attempt + 1,
                               "rejections": rejections, "source": self.llm.name}
            rejections.append({"attempt": attempt + 1, "text": draft.get("text", ""), "issues": issues})
            feedback = issues
        draft = fallback()
        return draft, {"verified": not self.verifier.check(draft, facts),
                       "attempts": self.max_attempts, "rejections": rejections,
                       "source": "template-fallback"}

    def _card(self, m: dict, persona: Persona) -> dict:
        analysis = self.analyst.analyze(m, self.detector)
        facts = {**m["facts"], **analysis}
        safe = Narrator(self._safe)
        draft, verification = self._loop(
            lambda a, fb: self.narrator.write(m, analysis, persona, a, fb),
            lambda: safe.write(m, analysis, persona, 1, []), facts)
        dur = 12 if m["type"] == "goal" else 8
        return {"moment_id": m["id"], "type": m["type"], "clock": m["clock"], "t": m["t"],
                "importance": m["importance"], "team": m["team"], "text": draft.get("text", ""),
                "language": persona.language, "depth": persona.depth,
                "evidence": m["evidence"], "facts": m["facts"], "analysis": analysis,
                "verification": verification,
                "overlay": {"id": f"ov-{m['id']}-{persona.id}", "layer": LAYER[m["type"]],
                            "title": TITLE[persona.language][m["type"]], "body": draft.get("text", ""),
                            "t_in": m["t"], "t_out": round(m["t"] + dur, 1),
                            "accent": self.colors.get(m["team"], "#888888"),
                            "priority": m["importance"], "evidence": m["evidence"]}}


    def recap(self, persona: Persona, cache: dict | None = None) -> dict:
        if cache is not None and "__recap__" in cache:
            return cache["__recap__"]
        result = self._recap(persona)
        if cache is not None:
            cache["__recap__"] = result
        return result




    def recap(self, persona: Persona) -> dict:
        s = self.detector.state.snapshot()
        h, a = self.home, self.away
        hg, ag = s["score"][h], s["score"][a]
        scorers = [f"{m.facts['scorer']} ({m.facts['team']}) {m.facts['clock']}"
                   for m in self.detector.moments if m.type == "goal"]
        facts = {"score": f"{hg}-{ag}", "score_line": f"{self.names[h]} {hg}-{ag} {self.names[a]}",
                 "home": self.names[h], "away": self.names[a],
                 "winner": self.names[h] if hg > ag else self.names[a] if ag > hg else "draw",
                 "home_shots": s["teams"][h]["shots"], "away_shots": s["teams"][a]["shots"],
                 "home_xg": s["teams"][h]["xg"], "away_xg": s["teams"][a]["xg"],
                 "home_possession_pct": s["teams"][h]["possession_pct"], "scorers": scorers}
        safe = RecapWriter(self._safe)
        draft, verification = self._loop(
            lambda at, fb: self.recapper.write(facts, persona, at, fb),
            lambda: safe.write(facts, persona, 1, []), facts)
        return {"text": draft.get("text", ""), "facts": facts, "verification": verification}