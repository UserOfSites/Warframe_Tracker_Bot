from dataclasses import dataclass, field
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
    """What `/fissures` renders — four sections plus per-era reset timers.

    - normal:      fast-type, not SP
    - steel_path:  fast-type, SP, not in dojoshare/defence lists
    - defences:    node in defence list, any mission type, Normal *and* SP
    - dojoshare:   SP only, node in dojoshare list, any mission type
    - cascade:     SP Void Cascade (Tuvul Commons) — a fixed standalone section
    - next_resets: one entry per (era, is_steel_path) combo that's currently
                   active, with the soonest expiry of that combo

    ``defences`` / ``cascade`` are defaulted so older constructors that predate
    those sections keep working (they get an empty list).
    """

    normal: list[Fissure]
    steel_path: list[Fissure]
    dojoshare: list[Fissure]
    next_resets: list[NextReset]
    generated_at: datetime
    defences: list[Fissure] = field(default_factory=list)
    cascade: list[Fissure] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (
            self.normal or self.steel_path or self.defences
            or self.dojoshare or self.cascade
        )
