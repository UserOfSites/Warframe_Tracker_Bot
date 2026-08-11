"""Static / lightly-fetched vendor facts shown alongside Baro Ki'Teer.

Three extra vendors ride along in the ``/vendors`` embed:

- **Teshin** (Steel Path Honors): an 8-week reward rotation.
- **Archon Hunt**: which Archon is up this week determines the Archon Shard
  colour you earn. That Archon → shard mapping is fixed by DE; only *which*
  Archon is current gets fetched live (see :func:`resolve_archon`).
- **Shiny Treasures**: a *separate* shard offering (unrelated to the Archon
  Hunt above) on its own 3-week blue → amber → crimson rotation.

Unlike the retired hourly Ayatan predictor, these are **weekly** rotations
anchored to Warframe's Monday-00:00-UTC reset (the same boundary the live
Archon Hunt payload uses), so they're far less fragile: one known week pins the
whole cycle. Update an entry's list/anchor only if DE reorders a rotation.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Warframe's weekly reset is Monday 00:00 UTC; every weekly rotation advances
# one step there. Anchored to the week beginning Monday 2026-08-10, which the
# operator confirmed offered Teshin "3× Forma" and a blue (Azure) Shiny shard.
_ROTATION_ANCHOR = datetime(2026, 8, 10, tzinfo=timezone.utc)


def _weeks_since_anchor(now: datetime | None) -> int:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta = now.astimezone(timezone.utc) - _ROTATION_ANCHOR
    return delta.days // 7  # floor division → correct on either side of anchor


# --- Teshin (Steel Path Honors) ----------------------------------------------


@dataclass(frozen=True)
class TeshinReward:
    name: str  # "3× Forma"
    icon_key: str  # emoji-registry key ("forma" / "umbra_forma" / "endo" / …)
    fallback_emoji: str  # unicode shown when the custom emoji isn't loaded


# Teshin's 8-week Steel Path Honors rotation, in order. Riven rewards share the
# generic riven icon; Kuva/Endo/Forma use their own.
_TESHIN_ROTATION: tuple[TeshinReward, ...] = (
    TeshinReward("Umbra Forma", "umbra_forma", "🔧"),
    TeshinReward("50,000 Kuva", "kuva", "🩸"),
    TeshinReward("Kitgun Riven Mod", "riven", "🟪"),
    TeshinReward("3× Forma", "forma", "🔧"),
    TeshinReward("Zaw Riven Mod", "riven", "🟪"),
    TeshinReward("30,000 Endo", "endo", "🔷"),
    TeshinReward("Rifle Riven Mod", "riven", "🟪"),
    TeshinReward("Shotgun Riven Mod", "riven", "🟪"),
)
# Index offered during the anchor week ("3× Forma").
_TESHIN_ANCHOR_INDEX = 3


def current_teshin_reward(now: datetime | None = None) -> TeshinReward:
    idx = (_TESHIN_ANCHOR_INDEX + _weeks_since_anchor(now)) % len(_TESHIN_ROTATION)
    return _TESHIN_ROTATION[idx]


# --- Archon Hunt (fetched live) ----------------------------------------------


@dataclass(frozen=True)
class ArchonShard:
    archon: str  # "Boreal"
    shard_name: str  # "Azure Archon Shard"
    color: str  # human word: "blue"
    emoji: str  # coloured circle, a text fallback for the real shard icon
    icon_key: str  # emoji-registry key for the real in-game shard icon


# DE fixes which Archon awards which shard colour: Amar → Crimson (red),
# Nira → Amber, Boreal (the bird) → Azure (blue). Matched by a lowercase
# substring so we're robust to the upstream returning "Boreal",
# "Archon Boreal", "Boreal, the ..." and so on.
_ARCHON_SHARDS: tuple[ArchonShard, ...] = (
    ArchonShard("Amar", "Crimson Archon Shard", "red", "🔴", "archon_shard_crimson"),
    ArchonShard("Nira", "Amber Archon Shard", "amber", "🟡", "archon_shard_amber"),
    ArchonShard("Boreal", "Azure Archon Shard", "blue", "🔵", "archon_shard_azure"),
)


def resolve_archon(boss_raw: str | None) -> ArchonShard | None:
    """Map an Archon-Hunt boss name to its Archon Shard, or ``None`` if the
    name is missing/unrecognised (the embed then just omits the line)."""
    if not boss_raw:
        return None
    needle = boss_raw.lower()
    for shard in _ARCHON_SHARDS:
        if shard.archon.lower() in needle:
            return shard
    return None


# --- Shiny Treasures (its own shard rotation) --------------------------------


@dataclass(frozen=True)
class ShardOffer:
    """A standalone shard on sale, decoupled from the Archon Hunt."""

    shard_name: str  # "Azure Archon Shard"
    color: str  # "blue"
    icon_key: str  # emoji-registry key for the real in-game shard icon
    fallback_emoji: str  # coloured circle shown when the custom emoji isn't loaded


# "Shiny Treasures" is its own vendor, separate from the weekly Archon Hunt, on
# a 3-week blue → amber(yellow) → crimson(red) rotation.
_SHINY_TREASURES_ROTATION: tuple[ShardOffer, ...] = (
    ShardOffer("Azure Archon Shard", "blue", "archon_shard_azure", "🔵"),
    ShardOffer("Amber Archon Shard", "amber", "archon_shard_amber", "🟡"),
    ShardOffer("Crimson Archon Shard", "red", "archon_shard_crimson", "🔴"),
)
# Index offered during the anchor week (Azure/blue).
_SHINY_TREASURES_ANCHOR_INDEX = 0


def current_shiny_treasure_shard(now: datetime | None = None) -> ShardOffer:
    idx = (_SHINY_TREASURES_ANCHOR_INDEX + _weeks_since_anchor(now)) % len(
        _SHINY_TREASURES_ROTATION
    )
    return _SHINY_TREASURES_ROTATION[idx]
