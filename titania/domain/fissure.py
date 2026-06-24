from dataclasses import dataclass
from datetime import datetime

from titania.domain.era import Era
from titania.domain.mission_type import MissionType


@dataclass(frozen=True)
class Fissure:
    era: Era
    mission_type: MissionType
    node: str
    planet: str
    expires_at: datetime  # UTC
    is_steel_path: bool
    is_hard: bool  # storm fissure / requiem etc.
    tier: int  # 1..6, matches ERA_TIER


@dataclass(frozen=True)
class NextReset:
    """Soonest expiry for a given (era, difficulty) — i.e. when that era's
    fissure pool next rotates. Computed from ALL active fissures, not the
    filtered sections, so the timer reflects the real game state."""

    era: Era
    is_steel_path: bool
    expires_at: datetime


@dataclass(frozen=True)
class FissureBoard:
    """What `/fissures` renders — three sections plus per-era reset timers.

    - normal:      fast-type, not SP
    - steel_path:  fast-type, SP, not in dojoshare list
    - dojoshare:   SP only, node in dojoshare list, any mission type
    - next_resets: one entry per (era, is_steel_path) combo that's currently
                   active, with the soonest expiry of that combo
    """

    normal: list[Fissure]
    steel_path: list[Fissure]
    dojoshare: list[Fissure]
    next_resets: list[NextReset]
    generated_at: datetime

    @property
    def is_empty(self) -> bool:
        return not (self.normal or self.steel_path or self.dojoshare)
