from datetime import datetime, timezone

from titania.domain.era import Era
from titania.domain.fissure import Fissure
from titania.domain.mission_type import MissionType
from titania.domain.railjack import is_railjack


def _fissure(
    *,
    mission_type: MissionType = MissionType.EXTERMINATE,
    node: str = "Hepit",
    planet: str = "Void",
    is_steel_path: bool = False,
) -> Fissure:
    return Fissure(
        era=Era.LITH,
        mission_type=mission_type,
        node=node,
        planet=planet,
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        is_steel_path=is_steel_path,
        is_hard=False,
        tier=1,
    )


def test_skirmish_mission_type_is_railjack():
    assert is_railjack(_fissure(mission_type=MissionType.SKIRMISH))


def test_volatile_mission_type_is_railjack():
    assert is_railjack(_fissure(mission_type=MissionType.VOLATILE))


def test_orphix_mission_type_is_railjack():
    assert is_railjack(_fissure(mission_type=MissionType.ORPHIX))


def test_exterminate_at_railjack_node_is_railjack():
    # Bifrost Echo (Venus) is a Venus Proxima node — its Extermination fissure
    # is still railjack mechanically, even though Extermination is a fast type.
    assert is_railjack(_fissure(mission_type=MissionType.EXTERMINATE, node="Bifrost Echo"))


def test_regular_extermination_at_regular_node_is_not_railjack():
    assert not is_railjack(
        _fissure(mission_type=MissionType.EXTERMINATE, node="Hepit", planet="Void")
    )


def test_survival_at_railjack_node_is_railjack():
    assert is_railjack(_fissure(mission_type=MissionType.SURVIVAL, node="Luckless Expanse"))


def test_dojoshare_node_is_not_railjack():
    # Sanity check: none of the dojoshare nodes overlap with railjack nodes.
    from titania.domain.mission_type import DEFAULT_DOJOSHARE_NODES
    from titania.domain.railjack import RAILJACK_NODES

    assert DEFAULT_DOJOSHARE_NODES.isdisjoint(RAILJACK_NODES)
