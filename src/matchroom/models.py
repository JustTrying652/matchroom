"""Plain data models shared by the whole pipeline."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Player:
    id: str
    name: str
    number: int
    position: str
    base_x: float  # typical x position when the player's team is attacking


@dataclass
class Team:
    code: str
    name: str
    color: str
    attack: float
    control: float
    press: float
    finishing: float
    players: list[Player] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Event:
    id: str
    t: float            # seconds of continuous play since kick-off (includes stoppage)
    minute: int         # match minute shown on screen (1-45 / 46-90)
    clock: str          # "12'", "45+2'"
    period: int
    type: str           # pass, shot, goal, tackle, interception, foul, card, corner, save,
                        # pressure, sprint, possession_change, period_start, period_end
    team: str           # team that performed the event
    poss: str           # team in possession when it happened
    player_id: Optional[str] = None
    player: Optional[str] = None
    x: float = 0.0      # absolute pitch metres (105 x 68); home attacks towards x=105
    y: float = 0.0
    end_x: Optional[float] = None
    end_y: Optional[float] = None
    outcome: Optional[str] = None
    recipient_id: Optional[str] = None
    recipient: Optional[str] = None
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)