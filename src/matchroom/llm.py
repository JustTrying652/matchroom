"""LLM access.

MockLLM runs fully offline with deterministic templates (English and Swahili), so
the whole pipeline can be built and tested without any account. AzureOpenAILLM
talks to Azure OpenAI / Microsoft Foundry. get_llm() picks Azure automatically
when its environment variables are set.
"""
from __future__ import annotations

import json
import os

STATE_SW = {"controlled": "umedhibitiwa", "balanced": "wa usawa", "chaotic": "wa vurugu"}
OUT_SW = {"saved": "limeokolewa", "blocked": "limezuiwa", "off target": "limetoka nje"}
CTX_SW = {"opening goal": "bao la kwanza", "equaliser": "bao la kusawazisha",
          "takes the lead": "bao la kuongoza", "pulls one back": "bao la kupunguza pengo",
          "extends the lead": "bao la kuongeza uongozi"}


def _n(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def _why_en(d):
    return (f" Why it matters: {_n(d['team_shots_5min'], 'shot')} worth {d['team_xg_5min']} xG in the "
            f"last {d['window_min']} minutes, in a {d['game_state']} match.")


def _why_sw(d):
    return (f" Kwa nini ni muhimu: mashuti {d['team_shots_5min']} (xG {d['team_xg_5min']}) katika "
            f"dakika {d['window_min']} zilizopita, mchezo ukiwa {STATE_SW[d['game_state']]}.")


def _en(typ, d, deep):
    f: list[str] = []
    if typ == "goal":
        t = f"GOAL at {d['clock']}! {d['scorer']} scores for {d['team']} ({d['context']}). It is {d['score']}."
        f = ["scorer", "team", "clock", "score", "context"]
        if d.get("assist"):
            t += f" Assisted by {d['assist']}."
            f.append("assist")
        if d.get("goals_in_match", 1) > 1:
            t += f" That is goal number {d['goals_in_match']} for him today."
            f.append("goals_in_match")
        if deep:
            t += (f" The shot was worth {d['xg']} xG, struck at {d['shot_speed_kmh']} km/h "
                  f"from {d['distance_m']} m.") + _why_en(d)
            f += ["xg", "shot_speed_kmh", "distance_m"]
    elif typ == "big_chance":
        t = f"Big chance at {d['clock']}! {d['player']} ({d['team']}) shoots and it is {d['outcome']}."
        f = ["player", "team", "clock", "outcome"]
        if deep:
            t += f" A {d['xg']} xG chance from {d['distance_m']} m, hit at {d['shot_speed_kmh']} km/h." + _why_en(d)
            f += ["xg", "distance_m", "shot_speed_kmh"]
    elif typ == "card":
        t = f"Yellow card at {d['clock']} for {d['player']} ({d['team']})."
        f = ["player", "team", "clock"]
    elif typ == "sprint":
        t = f"{d['player']} ({d['team']}) is flying: {d['speed_kmh']} km/h over {d['distance_m']} m."
        f = ["player", "team", "speed_kmh", "distance_m"]
    elif typ == "momentum_swing":
        t = (f"{d['team']} are taking over: {_n(d['shots_5min'], 'shot')} and {_n(d['corners_5min'], 'corner')} "
             f"in the last {d['window_min']} minutes.")
        f = ["team", "shots_5min", "corners_5min"]
        if deep:
            t += f" Momentum index {d['momentum_index']}, xG {d['xg_5min']}."
            f += ["momentum_index", "xg_5min"]
    elif typ == "chaos_phase":
        t = f"The match is getting stretched: the ball is changing hands {d['turnovers_per_min']} times a minute."
        f = ["turnovers_per_min"]
        if deep:
            t += f" Rhythm: {d['rhythm']}, {d['passes_per_min']} passes a minute."
            f += ["rhythm", "passes_per_min"]
    elif typ == "control_phase":
        t = f"{d['team']} are in control, with {d['share_pct']}% of the ball recently."
        f = ["team", "share_pct"]
        if deep:
            t += f" {d['passes_per_min']} passes a minute and a {d['rhythm']} rhythm."
            f += ["passes_per_min", "rhythm"]
    else:  # half_time / full_time
        word = "Half-time" if typ == "half_time" else "Full-time"
        t = f"{word}: {d['score_line']}."
        f = ["score"]
        if deep:
            t += (f" Shots {d['home_shots']}-{d['away_shots']}, xG {d['home_xg']}-{d['away_xg']}, "
                  f"possession {d['home_possession_pct']}%-{d['away_possession_pct']}%.")
            f += ["home_shots", "away_shots", "home_xg", "away_xg"]
    return t, f


def _sw(typ, d, deep):
    f: list[str] = []
    if typ == "goal":
        t = (f"MAGOLI! Dakika ya {d['minute']}, {d['scorer']} anaifungia {d['team']}: "
             f"{CTX_SW[d['context']]}. Matokeo ni {d['score']}.")
        f = ["scorer", "team", "minute", "score"]
        if d.get("assist"):
            t += f" Pasi ya {d['assist']}."
            f.append("assist")
        if d.get("goals_in_match", 1) > 1:
            t += f" Hili ni bao lake la {d['goals_in_match']} leo."
            f.append("goals_in_match")
        if deep:
            t += (f" Shuti lilikuwa na xG {d['xg']}, kasi ya {d['shot_speed_kmh']} km/h "
                  f"kutoka mita {d['distance_m']}.") + _why_sw(d)
            f += ["xg", "shot_speed_kmh", "distance_m"]
    elif typ == "big_chance":
        t = (f"Nafasi kubwa! Dakika ya {d['minute']}, {d['player']} ({d['team']}) "
             f"anapiga shuti: {OUT_SW.get(d['outcome'], d['outcome'])}.")
        f = ["player", "team", "minute"]
        if deep:
            t += f" Nafasi ya xG {d['xg']} kutoka mita {d['distance_m']}." + _why_sw(d)
            f += ["xg", "distance_m"]
    elif typ == "card":
        t = f"Kadi ya njano dakika ya {d['minute']} kwa {d['player']} ({d['team']})."
        f = ["player", "team", "minute"]
    elif typ == "sprint":
        t = f"{d['player']} ({d['team']}) anakimbia kwa kasi ya {d['speed_kmh']} km/h kwa mita {d['distance_m']}."
        f = ["player", "team", "speed_kmh", "distance_m"]
    elif typ == "momentum_swing":
        t = (f"{d['team']} wanatawala mchezo: mashuti {d['shots_5min']} na kona {d['corners_5min']} "
             f"katika dakika {d['window_min']} zilizopita.")
        f = ["team", "shots_5min", "corners_5min"]
        if deep:
            t += f" Kiwango cha kasi ya mchezo {d['momentum_index']}, xG {d['xg_5min']}."
            f += ["momentum_index", "xg_5min"]
    elif typ == "chaos_phase":
        t = f"Mchezo umechanganyikana: mpira unabadilisha mikono mara {d['turnovers_per_min']} kwa dakika."
        f = ["turnovers_per_min"]
        if deep:
            t += f" Pasi {d['passes_per_min']} kwa dakika."
            f.append("passes_per_min")
    elif typ == "control_phase":
        t = f"{d['team']} wanadhibiti mpira: {d['share_pct']}% ya umiliki hivi karibuni."
        f = ["team", "share_pct"]
        if deep:
            t += f" Pasi {d['passes_per_min']} kwa dakika."
            f.append("passes_per_min")
    else:
        word = "Mapumziko" if typ == "half_time" else "Mwisho wa mchezo"
        t = f"{word}: {d['score_line']}."
        f = ["score"]
        if deep:
            t += (f" Mashuti {d['home_shots']}-{d['away_shots']}, xG {d['home_xg']}-{d['away_xg']}, "
                  f"umiliki {d['home_possession_pct']}%-{d['away_possession_pct']}%.")
            f += ["home_shots", "away_shots", "home_xg", "away_xg"]
    return t, f


class MockLLM:
    name = "mock-templates"

    def __init__(self, inject_faults: bool = False):
        self.inject_faults = inject_faults   # demo mode: first goal draft contains wrong facts

    def complete(self, system: str, user: str, json_mode: bool = True, temperature: float = 0.4) -> str:
        p = json.loads(user.split("PAYLOAD:", 1)[1])
        out = self._commentary(p) if p["task"] == "commentary" else self._recap(p)
        return json.dumps(out, ensure_ascii=False)

    def _commentary(self, p):
        m, persona = p["moment"], p["persona"]
        d = {**m["facts"], **p["analysis"]}
        if self.inject_faults and m["type"] == "goal" and p["attempt"] == 0:
            d.update(clock="41'", minute=41, score="3-1")
        build = _sw if persona["language"] == "sw" else _en
        text, fields = build(m["type"], d, persona["depth"] == "analyst")
        return {"text": text, "claims": [{"field": k, "value": d[k]} for k in fields if d.get(k) is not None]}

    def _recap(self, p):
        f, sw = p["facts"], p["persona"]["language"] == "sw"
        scorers = "; ".join(f["scorers"]) if f["scorers"] else ("hakuna" if sw else "none")
        if sw:
            res = "Sare." if f["winner"] == "draw" else f"{f['winner']} wameshinda."
            text = (f"Mwisho wa mchezo: {f['score_line']}. {res} Wafungaji: {scorers}. "
                    f"{f['home']} walipiga mashuti {f['home_shots']} (xG {f['home_xg']}) dhidi ya "
                    f"{f['away_shots']} (xG {f['away_xg']}) za {f['away']}; umiliki {f['home_possession_pct']}%.")
        else:
            res = "The points are shared." if f["winner"] == "draw" else f"{f['winner']} take the win."
            text = (f"Full-time: {f['score_line']}. {res} Scorers: {scorers}. "
                    f"{f['home']} had {f['home_shots']} shots ({f['home_xg']} xG) to {f['away']}'s "
                    f"{f['away_shots']} ({f['away_xg']} xG), with {f['home_possession_pct']}% of possession.")
        return {"text": text, "claims": [{"field": k, "value": f[k]} for k in ("score", "home", "away")]}


class AzureOpenAILLM:
    """Azure OpenAI / Microsoft Foundry deployment (not yet tested: needs an Azure subscription)."""
    name = "azure-openai"

    def __init__(self):
        from openai import AzureOpenAI
        self.client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"))
        self.model = os.environ["AZURE_OPENAI_DEPLOYMENT"]

    def complete(self, system: str, user: str, json_mode: bool = True, temperature: float = 0.4) -> str:
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            r = self.client.chat.completions.create(model=self.model, messages=msgs,
                                                    temperature=temperature, **kwargs)
        except Exception:   # some models only accept the default temperature
            r = self.client.chat.completions.create(model=self.model, messages=msgs, **kwargs)
        return r.choices[0].message.content


def get_llm(inject_faults: bool = False):
    needed = ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT")
    if all(os.environ.get(k) for k in needed):
        return AzureOpenAILLM()
    return MockLLM(inject_faults)