from enum import StrEnum
from typing import Iterable

from titania.domain.fissure import Fissure
from titania.domain.mission_type import FAST_MISSIONS

_TUVUL_COMMONS_LC = "tuvul commons"


class FissureTopic(StrEnum):
    """Per-user subscription buckets exposed as buttons under the fissure tracker.

    Topics are evaluated independently of the per-guild display filters
    (``allowed_mission_types``, ``blocked_nodes``, ``pinned_nodes``) — opting
    in to a topic is itself the user's explicit signal of interest, so we
    don't second-guess it with display-time filtering.
    """

    NORMAL_FAST = "normal_fast"
    SP_FAST = "sp_fast"
    DOJOSHARE = "dojoshare"
    SP_TUVUL_CASCADE = "sp_tuvul_cascade"


TOPIC_LABELS: dict[FissureTopic, str] = {
    FissureTopic.NORMAL_FAST: "Normal Fast",
    FissureTopic.SP_FAST: "Steel Path Fast",
    FissureTopic.DOJOSHARE: "Dojoshare",
    FissureTopic.SP_TUVUL_CASCADE: "SP Tuvul Commons (Void Cascade)",
}


def fissure_matches_topic(
    f: Fissure,
    topic: FissureTopic,
    dojoshare_nodes: Iterable[str],
) -> bool:
    """True iff this fissure should fire a notification for the given topic."""
    node_lc = f.node.strip().lower()
    if topic is FissureTopic.NORMAL_FAST:
        return not f.is_steel_path and f.mission_type in FAST_MISSIONS
    if topic is FissureTopic.SP_FAST:
        # Mirror FissureService: dojoshare nodes have their own bucket and
        # shouldn't double-fire as SP-fast.
        ds = {n.strip().lower() for n in dojoshare_nodes}
        return (
            f.is_steel_path
            and f.mission_type in FAST_MISSIONS
            and node_lc not in ds
        )
    if topic is FissureTopic.DOJOSHARE:
        ds = {n.strip().lower() for n in dojoshare_nodes}
        return f.is_steel_path and node_lc in ds
    if topic is FissureTopic.SP_TUVUL_CASCADE:
        # Tuvul Commons IS the Void Cascade node — checking node alone is
        # sufficient and robust to MissionType.OTHER for new game modes.
        return f.is_steel_path and node_lc == _TUVUL_COMMONS_LC
    return False
