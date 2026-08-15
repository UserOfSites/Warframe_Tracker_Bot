"""Adapt Digital Extremes' raw worldState.php document into domain Fissures.

DE's format is very different from warframestat's clean JSON: fissures live in
``ActiveMissions`` keyed by ``SolNode`` id (no human node name), the era is a
``Modifier`` string (``VoidT1``..``VoidT6``), Steel Path is a bare ``Hard: true``
flag, and timestamps are Mongo-extended-JSON epoch-millis. Railjack (Void Storm)
fissures are *not* here — they live under a separate ``VoidStorms`` key with
``CrewBattleNode`` ids — so ``ActiveMissions`` is regular fissures only.

Node id -> (name, planet, mission-type) resolution needs the ``/solnodes``
catalog, which the caller supplies as ``node_map`` (that endpoint is static
reference data and stays live even when DE's live worldstate feed does not).
"""

from datetime import datetime, timezone
from typing import Any

from titania.domain.era import ERA_TIER, Era
from titania.domain.fissure import Fissure
from titania.domain.mission_type import MissionType, parse_mission_type

# ``Modifier`` era codes. VoidT5 is Requiem, VoidT6 is Omnia (Zariman / Lua).
_ERA_BY_MODIFIER: dict[str, Era] = {
    "VoidT1": Era.LITH,
    "VoidT2": Era.MESO,
    "VoidT3": Era.NEO,
    "VoidT4": Era.AXI,
    "VoidT5": Era.REQUIEM,
    "VoidT6": Era.OMNIA,
}


def _epoch_millis(node: dict[str, Any]) -> datetime | None:
    """Parse Mongo extended-JSON ``{"$date": {"$numberLong": "<ms>"}}``."""
    try:
        ms = node["$date"]["$numberLong"]
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except (KeyError, TypeError, ValueError):
        return None


def _mission_type_from_de(mt_raw: str) -> MissionType:
    """``'MT_MOBILE_DEFENSE'`` -> MissionType.MOBILE_DEFENSE. Falls back through
    the shared parser so unknown codes become ``OTHER`` rather than raising."""
    label = mt_raw.removeprefix("MT_").replace("_", " ").title()
    return parse_mission_type(label)


def adapt_worldstate_fissures(
    payload: dict[str, Any],
    node_map: dict[str, tuple[str, str, str]],
) -> list[Fissure]:
    """``payload`` is the full worldState.php document; ``node_map`` maps
    ``SolNode`` id -> ``(name, planet, mission_type_raw)`` from ``/solnodes``."""
    now = datetime.now(timezone.utc)
    out: list[Fissure] = []
    for item in payload.get("ActiveMissions", []):
        if not isinstance(item, dict):
            continue
        era = _ERA_BY_MODIFIER.get(item.get("Modifier", ""))
        if era is None:
            continue  # not a void fissure (defensive; ActiveMissions is fissures)
        expires_at = _epoch_millis(item.get("Expiry", {}))
        if expires_at is None:
            continue
        # Same defensive rule as the warframestat adapter: never ingest a fissure
        # whose window has already closed, so a stale feed can't pin the board.
        if expires_at <= now:
            continue

        node_id = item.get("Node", "")
        name, planet, type_raw = node_map.get(node_id, ("", "", ""))
        # Prefer the /solnodes mission type (already in our label vocabulary and
        # more specific, e.g. "Void Flood"); fall back to DE's MT_ code.
        if type_raw:
            mission_type = parse_mission_type(type_raw)
        else:
            mission_type = _mission_type_from_de(item.get("MissionType", ""))
        # If /solnodes can't name the node, degrade to the raw id rather than
        # dropping the fissure — better a slightly ugly node than a missing one.
        node = name or node_id

        out.append(
            Fissure(
                era=era,
                mission_type=mission_type,
                node=node,
                planet=planet,
                expires_at=expires_at,
                is_steel_path=bool(item.get("Hard", False)),
                is_hard=False,  # storms are VoidStorms, not ActiveMissions
                tier=ERA_TIER[era],
            )
        )
    return out
