"""Static / lightly-fetched vendor facts shown alongside Baro Ki'Teer.

Two extra vendors ride along in the ``/vendors`` embed:

- **Teshin** (Steel Path Honors): his weekly rotating reward. The rotation is
  a fixed community-known cycle, but rather than *predict* it — and risk the
  same drift the retired Ayatan predictor had — we pin the current week's item
  here and bump it by hand each week.
- **Archon Hunt**: which Archon is up this week determines the Archon Shard
  colour you earn. That Archon → shard mapping is fixed by DE; only *which*
  Archon is current gets fetched live.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TeshinReward:
    name: str  # "Forma Bundle"
    icon_key: str  # emoji-registry key ("forma" / "endo" / "riven" / …)
    fallback_emoji: str  # unicode shown when the custom emoji isn't loaded


# Teshin's current Steel Path Honors weekly reward. Update this by hand each
# week (Monday reset). Kept deliberately dumb-static — see module docstring.
# ``icon_key`` picks the real in-game icon; when the weekly rotates to Endo or
# a Riven Sliver, point it at "endo" / "riven".
TESHIN_WEEKLY = TeshinReward(name="Forma Bundle", icon_key="forma", fallback_emoji="🔧")


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
