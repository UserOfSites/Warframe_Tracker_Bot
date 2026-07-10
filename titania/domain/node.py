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
#   - ``Kuva Fortress``: only carries Requiem fissures, which are filtered
#     out globally as not relic-relevant.
#   - ``Duviri``: no regular fissure rotation, only the Circuit Steel Path
#     content which we don't track.
# Kept under 25 (Discord select-option cap) so it always fits a single row.
#
# ``Phobos`` is present but warframestat's /solnodes doesn't ship its
# entries (Tharsis, its sole surviving node in that endpoint, is filed as
# "Mars"). We keep Phobos in the list because its fissures *do* appear in
# the live ``/pc/fissures`` endpoint (Stickney, Roche, …), and users need
# to pin/block/rate them. See ``PHOBOS_FALLBACK_NODES`` below for the
# static list the panels merge in when the catalog can't cover it.
STAR_CHART_PLANETS: tuple[str, ...] = (
    "Mercury", "Venus", "Earth", "Lua", "Mars", "Phobos", "Deimos", "Ceres",
    "Jupiter", "Europa", "Saturn", "Uranus", "Neptune", "Pluto", "Sedna",
    "Eris", "Void", "Zariman",
)


# Canonical Phobos node names to populate the node dropdown when the /solnodes
# catalog draws a blank on Phobos (which is always, since warframestat files
# them under Mars). Mission types are intentionally left blank — Phobos nodes
# have shifted between mission types over Warframe patches, and the settings-
# panel filter treats blank mission types as "unknown, always show" so users
# can still pin/block them regardless of the current mission-type filter.
PHOBOS_FALLBACK_NODES: tuple[str, ...] = (
    "Gulliver",
    "Iliad",
    "Kepler",
    "Memphis",
    "Monolith",
    "Roche",
    "Shklovsky",
    "Skyresh",
    "Stickney",
    "Tharsis",
    "Womo",
    "Zeugma",
)
