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
