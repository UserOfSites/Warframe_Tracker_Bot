from enum import StrEnum


class MissionType(StrEnum):
    EXTERMINATE = "Exterminate"
    SABOTAGE = "Sabotage"
    CAPTURE = "Capture"
    DEFENSE = "Defense"
    SURVIVAL = "Survival"
    EXCAVATION = "Excavation"
    INTERCEPTION = "Interception"
    DISRUPTION = "Disruption"
    MOBILE_DEFENSE = "Mobile Defense"
    HIJACK = "Hijack"
    SPY = "Spy"
    RESCUE = "Rescue"
    DEFECTION = "Defection"
    ASSAULT = "Assault"
    SKIRMISH = "Skirmish"
    VOLATILE = "Volatile"
    ORPHIX = "Orphix"
    ALCHEMY = "Alchemy"
    OTHER = "Other"


# Spy and Rescue are intentionally excluded — short but objective-gated.
FAST_MISSIONS: frozenset[MissionType] = frozenset({
    MissionType.EXTERMINATE,
    MissionType.SABOTAGE,
    MissionType.CAPTURE,
})


# Railjack-exclusive mission types. A fissure with any of these is always
# railjack regardless of node.
RAILJACK_MISSION_TYPES: frozenset[MissionType] = frozenset({
    MissionType.SKIRMISH,
    MissionType.VOLATILE,
    MissionType.ORPHIX,
})


# Steel-Path-only dojoshare nodes. Normal-difficulty fissures at these nodes
# follow the standard Normal-section rules (they are not promoted).
DEFAULT_DOJOSHARE_NODES: frozenset[str] = frozenset({
    # Ceres
    "Draco",        # Survival
    "Casta",        # Defense
    # Eris
    "Nimus",        # Survival
    # Void
    "Mot",          # Survival
    "Ani",          # Defense
    # Jupiter
    "Elara",        # Survival
    "Io",           # Defense
    # Uranus
    "Stephano",     # Defense
    # Lua
    "Circulus",     # Omnia Survival
    "Yuvarium",     # Omnia Survival
})


# Upstream labels that don't match enum values verbatim (e.g. warframestat returns
# "Extermination" while the in-game label is "Exterminate").
_MISSION_TYPE_ALIASES: dict[str, MissionType] = {
    "extermination": MissionType.EXTERMINATE,
    "mobiledefense": MissionType.MOBILE_DEFENSE,
}


def parse_mission_type(raw: str) -> MissionType:
    """Map a free-form mission name to a MissionType; unknown values become OTHER."""
    normalized = raw.strip().lower()
    if alias := _MISSION_TYPE_ALIASES.get(normalized.replace(" ", "")):
        return alias
    for mt in MissionType:
        if mt.value.lower() == normalized:
            return mt
    return MissionType.OTHER
