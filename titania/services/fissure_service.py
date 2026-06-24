from datetime import datetime, timezone

from titania.data.source import WarframeDataSource
from titania.domain.era import ERA_TIER, Era
from titania.domain.fissure import Fissure, FissureBoard, NextReset
from titania.domain.railjack import is_railjack
from titania.services.guild_settings import GuildSettingsResolver


def _normalize(node: str) -> str:
    return node.strip().lower()


def _sort_key(f: Fissure) -> tuple[int, datetime]:
    return (f.tier, f.expires_at)


def _compute_next_resets(fissures: list[Fissure]) -> list[NextReset]:
    soonest: dict[tuple[Era, bool], datetime] = {}
    for f in fissures:
        key = (f.era, f.is_steel_path)
        if key not in soonest or f.expires_at < soonest[key]:
            soonest[key] = f.expires_at
    resets = [
        NextReset(era=era, is_steel_path=sp, expires_at=t)
        for (era, sp), t in soonest.items()
    ]
    # Normal first, Steel Path second; within each, by era tier (Lith → Omnia).
    resets.sort(key=lambda r: (r.is_steel_path, ERA_TIER[r.era]))
    return resets


class FissureService:
    """Builds the FissureBoard a guild sees.

    Single-pass partition with explicit priority:
      1. Dojoshare:  is_steel_path AND node in dojoshare_nodes
      2. Steel Path: is_steel_path AND mission_type in allowed AND node not blocked
      3. Normal:    !is_steel_path AND mission_type in allowed AND node not blocked
      otherwise: dropped.

    The dojoshare bucket bypasses the mission-type filter and the blocked-nodes
    list — it is an explicit per-node opt-in for long Steel Path farms. Normal-
    difficulty fissures at dojoshare nodes are NOT promoted; they fall through
    to the standard Normal-section rules (so under the default mission-type
    filter they are dropped, since none of the default dojoshare nodes are
    fast-type missions).
    """

    def __init__(
        self,
        data_source: WarframeDataSource,
        settings_resolver: GuildSettingsResolver,
    ) -> None:
        self._source = data_source
        self._settings_resolver = settings_resolver

    async def board_for_guild(self, guild_id: int | None) -> FissureBoard:
        settings = await self._settings_resolver(guild_id)
        # Drop railjack (mechanically different) and Requiem (useless for
        # relic farming) at the source, so neither leaks into the partition
        # or the next-reset timers.
        all_fissures = [
            f
            for f in await self._source.fetch_fissures()
            if not is_railjack(f) and f.era is not Era.REQUIEM
        ]

        allowed_types = settings.allowed_mission_types
        blocked = {_normalize(n) for n in settings.blocked_nodes}
        pinned = {_normalize(n) for n in settings.pinned_nodes}
        dojoshare_set = {_normalize(n) for n in settings.dojoshare_nodes}

        normal: list[Fissure] = []
        steel_path: list[Fissure] = []
        dojoshare: list[Fissure] = []

        for f in all_fissures:
            node_lc = _normalize(f.node)
            if f.is_steel_path and node_lc in dojoshare_set:
                dojoshare.append(f)
                continue
            # Pinned nodes bypass the type filter — they are an explicit
            # always-show override. Blocked still wins (defensive: if a node
            # is in both lists, the user's most recent intent isn't clear, so
            # we err on the side of hiding).
            if node_lc in blocked:
                continue
            if node_lc not in pinned and f.mission_type not in allowed_types:
                continue
            if f.is_steel_path:
                steel_path.append(f)
            else:
                normal.append(f)

        normal.sort(key=_sort_key)
        steel_path.sort(key=_sort_key)
        dojoshare.sort(key=_sort_key)

        return FissureBoard(
            normal=normal,
            steel_path=steel_path,
            dojoshare=dojoshare,
            next_resets=_compute_next_resets(all_fissures),
            generated_at=datetime.now(timezone.utc),
        )
