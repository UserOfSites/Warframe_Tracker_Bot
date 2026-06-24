from titania.domain.fissure import Fissure
from titania.domain.mission_type import RAILJACK_MISSION_TYPES

# Bare node names (without planet suffix) for every Railjack node, sourced from
# api.warframestat.us/solnodes where Railjack nodes are keyed `CrewBattleNode*`
# (vs `SolNode*` for regular missions). Railjack hasn't received new nodes in
# years; if it ever does, refresh with:
#
#   curl -s https://api.warframestat.us/solnodes \
#     | jq -r 'to_entries[] | select(.key|startswith("CrewBattleNode")) | .value.value' \
#     | sed 's/ (.*//' | sort -u
RAILJACK_NODES: frozenset[str] = frozenset({
    "Arc Silver",
    "Arva Vector",
    "Beacon Shield Ring",
    "Bendar Cluster",
    "Bifrost Echo",
    "Brom Cluster",
    "Calabash",
    "Enkidu Ice Drifts",
    "Erato",
    "Falling Glory",
    "Fenton's Field",
    "Flexa",
    "Ganalen's Grave",
    "Gian Point",
    "H-2 Cloud",
    "Iota Temple",
    "Kasio's Rest",
    "Khufu Envoy",
    "Korm's Belt",
    "Lu-yan",
    "Luckless Expanse",
    "Lupal Pass",
    "Mammon's Prospect",
    "Mordo Cluster",
    "Nodo Gap",
    "Nsu Grid",
    "Nu-gua Mines",
    "Numina",
    "Obol Crossing",
    "Ogal Cluster",
    "Orvin-Haarc",
    "Peregrine Axis",
    "Profit Margin",
    "R-9 Cloud",
    "Ruse War Field",
    "Rya",
    "Sambir Cloud",
    "Seven Sirens",
    "Sover Strait",
    "Sovereign Grasp",
    "Vand Cluster",
    "Vesper Strait",
})


def is_railjack(fissure: Fissure) -> bool:
    """A fissure is railjack if its mission type is railjack-exclusive
    (Skirmish / Volatile / Orphix) or its node is one of the Proxima nodes.
    Railjack is intentionally excluded from every section of /fissures: it
    isn't a fast clear like Exterminate, and it's not the kind of long farm
    dojoshare is designed around."""
    if fissure.mission_type in RAILJACK_MISSION_TYPES:
        return True
    return fissure.node in RAILJACK_NODES
