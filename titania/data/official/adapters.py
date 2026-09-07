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

import re
from datetime import datetime, timezone
from typing import Any

from titania.data.warframestat.source import _split_node_value
from titania.domain.era import ERA_TIER, Era
from titania.domain.fissure import Fissure
from titania.domain.mission_type import MissionType, parse_mission_type

# DE identifies Baro's relay by an internal hub key; map the seven to the
# human relay names (stable — relays effectively never change).
_RELAY_BY_HUB: dict[str, str] = {
    "MercuryHUB": "Larunda Relay (Mercury)",
    "VenusHUB": "Vesper Relay (Venus)",
    "EarthHUB": "Strata Relay (Earth)",
    "SaturnHUB": "Kronia Relay (Saturn)",
    "ErisHUB": "Kuiper Relay (Eris)",
    "EuropaHUB": "Leonov Relay (Europa)",
    "PlutoHUB": "Orcus Relay (Pluto)",
}

_CAMEL_SPLIT = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")

# Star-chart node-key prefixes that host regular missions (and therefore
# fissures). Phobos is the odd one out — its nodes use the historical
# ``SettlementNode*`` keys; every other planet is ``SolNode*``. Miss a prefix
# and those fissures fall back to showing their raw id (e.g. "SettlementNode2"
# instead of "Skyresh (Phobos)").
_MISSION_NODE_PREFIXES = ("SolNode", "SettlementNode")


def build_node_map(payload: dict[str, Any]) -> dict[str, tuple[str, str, str]]:
    """``/solnodes`` payload -> ``{node id: (name, planet, mission_type_raw)}``
    for every regular mission node. DE's worldstate references fissure nodes by
    these ids, so the map must cover every star-chart prefix, Phobos included."""
    out: dict[str, tuple[str, str, str]] = {}
    for key, entry in payload.items():
        if not (isinstance(entry, dict) and key.startswith(_MISSION_NODE_PREFIXES)):
            continue
        value = entry.get("value")
        if not (isinstance(value, str) and "(" in value):
            continue
        name, planet = _split_node_value(value)
        mt_raw = entry.get("type")
        out[key] = (name, planet, mt_raw if isinstance(mt_raw, str) else "")
    return out


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


def _name_from_lotus_path(path: str) -> str:
    """Best-effort readable name from a Lotus item path. DE doesn't ship the
    friendly names warframestat resolves, so this is a degraded stand-in used
    only when failing over to DE for Baro's inventory:
    ``".../MPVBansheePrimeSinglePack"`` -> ``"MPV Banshee Prime Single Pack"``."""
    leaf = path.rstrip("/").rsplit("/", 1)[-1]
    words = _CAMEL_SPLIT.findall(leaf)
    return " ".join(words) if words else leaf


def adapt_void_trader(payload: dict[str, Any]) -> dict[str, Any]:
    """DE ``VoidTraders`` -> warframestat ``voidTrader`` shape. Item names are
    approximate (Lotus paths), but the summary line only needs the window +
    relay, and presence is inferred from a non-empty inventory (the ``Manifest``
    is present only while Baro is here)."""
    traders = payload.get("VoidTraders") or []
    if not traders or not isinstance(traders[0], dict):
        return {}
    t = traders[0]
    activation = _epoch_millis(t.get("Activation", {}))
    expiry = _epoch_millis(t.get("Expiry", {}))
    inventory = [
        {"item": _name_from_lotus_path(m["ItemType"]), "ducats": m.get("PrimePrice")}
        for m in (t.get("Manifest") or [])
        if isinstance(m, dict) and isinstance(m.get("ItemType"), str)
    ]
    node = t.get("Node", "")
    return {
        "character": "Baro Ki'Teer",
        "location": _RELAY_BY_HUB.get(node, node),
        "activation": activation.isoformat() if activation else None,
        "expiry": expiry.isoformat() if expiry else None,
        "inventory": inventory,
    }


def adapt_archon_hunt(payload: dict[str, Any]) -> dict[str, Any]:
    """DE ``LiteSorties`` -> ``{"boss": ...}``. The boss enum
    (``SORTIE_BOSS_AMAR``) contains the Archon name, which ``resolve_archon``
    already matches as a substring, so no explicit mapping is needed."""
    sorties = payload.get("LiteSorties") or []
    if not sorties or not isinstance(sorties[0], dict):
        return {}
    boss = sorties[0].get("Boss")
    return {"boss": boss} if isinstance(boss, str) else {}
