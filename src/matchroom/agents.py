"""The agents. Each has one job and talks to the others through plain data.

Analyst      : works out WHY a moment matters, from numbers (no LLM, no guessing).
Narrator     : writes the on-screen line for one fan persona (LLM).
Verifier     : checks every claim and number against the data; rejects bad drafts.
RecapWriter  : writes the full-time recap (LLM), checked by the same Verifier.
Personalizer : decides which moments a given fan should see.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

NARRATOR_SYSTEM = """You are the Narrator on a live football broadcast desk. Write ONE short on-screen \
commentary item for a single moment, using ONLY the facts in the payload. Never invent players, \
minutes, scores, teams or numbers. Write in the requested language. depth "casual" means one or two \
short, friendly sentences for a casual fan; depth "analyst" means up to three sentences with the \
supporting numbers and why it matters. If "feedback" is present, your previous draft was rejected: \
fix every problem listed. Reply with JSON only: {"text": string, "claims": [{"field": string, \
"value": string|number}]}, where each claim restates a fact you used with the exact field name and \
value from the payload."""

RECAP_SYSTEM = """You are the Recap Writer for a football broadcast desk. Write a short full-time \
recap (3-4 sentences) using ONLY the facts in the payload, in the requested language. Never invent \
players, scores or numbers. If "feedback" is present, fix every problem listed. Reply with JSON \
only: {"text": string, "claims": [{"field": string, "value": string|number}]} with claims for \
score, home and away."""

NUM = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class Persona:
    id: str
    language: str = "en"          # "en" or "sw"
    depth: str = "casual"         # "casual" or "analyst"
    favorite_club: str | None = None   # team code, e.g. "LKU"
    focus_player: str | None = None    # full name: only that player's moments (plus goals / results)


PERSONAS = {
    "casual_en": Persona("casual_en"),
    "analyst_en": Persona("analyst_en", depth="analyst"),
    "casual_sw": Persona("casual_sw", language="sw"),
    "analyst_sw": Persona("analyst_sw", language="sw", depth="analyst"),
}


# --------------------------------------------------------------------- Analyst
class Analyst:
    def __init__(self, names: dict[str, str]):
        self.names = names

    def analyze(self, m: dict, det) -> dict:
        mom = det.state.momentum()
        cvc = det.state.control_vs_chaos()
        shots = [e for e in det.recent if e["type"] == "shot" and e["team"] == m["team"]] if m["team"] else []
        return {"window_min": 5, "momentum_index": mom["index"],
                "momentum_leader": self.names.get(mom["leader"], "neither side"),
                "team_shots_5min": len(shots),
                "team_xg_5min": round(sum(e["metrics"]["xg"] for e in shots), 2),
                "game_state": cvc["label"], "rhythm": cvc["rhythm"], "chaos_index": cvc["chaos_index"]}


# -------------------------------------------------------------------- Narrator
def _parse(raw: str) -> dict:
    try:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[-1]
        out = json.loads(raw)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


class Narrator:
    def __init__(self, llm):
        self.llm = llm

    def write(self, m: dict, analysis: dict, persona: Persona, attempt: int, feedback: list) -> dict:
        payload = {"task": "commentary", "moment": m, "analysis": analysis, "attempt": attempt,
                   "feedback": feedback,
                   "persona": {"language": persona.language, "depth": persona.depth,
                               "favorite_club": persona.favorite_club}}
        return _parse(self.llm.complete(NARRATOR_SYSTEM, "PAYLOAD:" + json.dumps(payload)))


class RecapWriter:
    def __init__(self, llm):
        self.llm = llm

    def write(self, facts: dict, persona: Persona, attempt: int, feedback: list) -> dict:
        payload = {"task": "recap", "facts": facts, "attempt": attempt, "feedback": feedback,
                   "persona": {"language": persona.language, "depth": persona.depth}}
        return _parse(self.llm.complete(RECAP_SYSTEM, "PAYLOAD:" + json.dumps(payload)))


# -------------------------------------------------------------------- Verifier
def _walk(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, (list, tuple)):
        for v in o:
            yield from _walk(v)
    else:
        yield o


def _same(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) < 0.051
    except (TypeError, ValueError):
        return str(a).strip().lower() == str(b).strip().lower()


def _num_eq(tok: str, allowed: str) -> bool:
    if float(tok) == float(allowed):
        return True
    return "." in tok and "." in allowed and abs(float(tok) - float(allowed)) <= 0.051


class Verifier:
    """Deterministic fact-checker: no model involved, so it cannot be talked round."""

    def __init__(self, roster: set[str]):
        self.roster = roster

    def check(self, draft: dict, facts: dict) -> list[str]:
        text, claims = draft.get("text"), draft.get("claims")
        if not isinstance(text, str) or not text.strip():
            return ["empty or missing text"]
        issues: list[str] = []
        if len(text) > 600:
            issues.append("text is too long")
        if not isinstance(claims, list) or not claims:
            issues.append("claims missing: list every fact you used")
        for c in claims if isinstance(claims, list) else []:
            if not isinstance(c, dict) or "field" not in c:
                issues.append("malformed claim")
                continue
            f, v = c["field"], c.get("value")
            if facts.get(f) is None:
                issues.append(f"claim '{f}' is not a known fact")
            elif not _same(v, facts[f]):
                issues.append(f"claim {f}={v!r} contradicts the data (correct value: {facts[f]!r})")
        allowed = {tok for leaf in _walk(facts) for tok in NUM.findall(str(leaf))}
        for tok in NUM.findall(text):
            if not any(_num_eq(tok, a) for a in allowed):
                issues.append(f"number {tok} in the text is not supported by the facts")
        known = [leaf for leaf in _walk(facts) if isinstance(leaf, str)]
        for name in self.roster:
            if name in text and not any(name in k for k in known):
                issues.append(f"mentions {name}, who is not part of this moment")
        return list(dict.fromkeys(issues))


# ---------------------------------------------------------------- Personalizer
class Personalizer:
    def wants(self, m: dict, p: Persona) -> bool:
        if p.focus_player:
            return m["player"] == p.focus_player or m["type"] in ("goal", "half_time", "full_time")
        score = m["importance"] + (0.2 if p.favorite_club and m["team"] == p.favorite_club else 0)
        return score >= (0.6 if p.depth == "casual" else 0.3)