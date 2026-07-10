from dataclasses import dataclass


@dataclass(frozen=True)
class NodeInfo:
    """Per-node metadata used by the filter panel to scope node dropdowns.

    ``mission_type_raw`` is the upstream string (e.g. "Capture", "Mobile
    Defense"); call ``parse_mission_type`` on it to map to the canonical
    ``MissionType`` enum.
    """

    name: str
    planet: str
    mission_type_raw: str


# Planets shown in the panel selectors, in Star-Chart progression order.
# Curated to planets that carry the fissure content Titania actually
# surfaces — omissions:
#   - ``Phobos``: warframestat's /solnodes no longer ships Phobos entries
#     (Tharsis, the sole surviving node, is tagged "Mars" upstream).
#   - ``Kuva Fortress``: only carries Requiem fissures, which are filtered
#     out globally as not relic-relevant.
#   - ``Duviri``: no regular fissure rotation, only the Circuit Steel Path
#     content which we don't track.
# Kept under 25 (Discord select-option cap) so it always fits a single row.
STAR_CHART_PLANETS: tuple[str, ...] = (
    "Mercury", "Venus", "Earth", "Lua", "Mars", "Deimos", "Ceres",
    "Jupiter", "Europa", "Saturn", "Uranus", "Neptune", "Pluto", "Sedna",
    "Eris", "Void", "Zariman",
)
