from datetime import datetime, timedelta, timezone

from titania.data.official.adapters import adapt_worldstate_fissures
from titania.domain.era import Era
from titania.domain.mission_type import MissionType

_NODE_MAP = {
    "SolNode1": ("Hepit", "Void", "Capture"),
    "SolNode2": ("Stephano", "Uranus", "Defense"),
    "SolNode3": ("Everview Arc", "Zariman", "Void Flood"),
}


def _ms(dt: datetime) -> dict:
    return {"$date": {"$numberLong": str(int(dt.timestamp() * 1000))}}


def _mission(node="SolNode1", modifier="VoidT1", hard=False, expires_in=timedelta(hours=1),
             mt="MT_CAPTURE"):
    return {
        "Node": node,
        "Modifier": modifier,
        "MissionType": mt,
        "Hard": hard,
        "Expiry": _ms(datetime.now(timezone.utc) + expires_in),
    }


def test_maps_era_node_and_steel_path():
    payload = {"ActiveMissions": [
        _mission(node="SolNode2", modifier="VoidT3", hard=True),
    ]}
    out = adapt_worldstate_fissures(payload, _NODE_MAP)
    assert len(out) == 1
    f = out[0]
    assert f.era is Era.NEO
    assert f.node == "Stephano" and f.planet == "Uranus"
    assert f.mission_type is MissionType.DEFENSE
    assert f.is_steel_path is True
    assert f.tier == 3


def test_voidt6_is_omnia():
    payload = {"ActiveMissions": [_mission(node="SolNode3", modifier="VoidT6")]}
    out = adapt_worldstate_fissures(payload, _NODE_MAP)
    assert out[0].era is Era.OMNIA


def test_drops_past_expiry():
    payload = {"ActiveMissions": [
        _mission(expires_in=timedelta(minutes=-5)),   # already closed
        _mission(node="SolNode2", modifier="VoidT2"),  # active
    ]}
    out = adapt_worldstate_fissures(payload, _NODE_MAP)
    assert len(out) == 1
    assert out[0].era is Era.MESO


def test_skips_non_void_and_malformed_entries():
    payload = {"ActiveMissions": [
        _mission(modifier="NotAVoidTier"),   # not a fissure
        {"Node": "SolNode1"},                # no Modifier/Expiry
        "garbage",                           # not a dict
    ]}
    assert adapt_worldstate_fissures(payload, _NODE_MAP) == []


def test_prefers_solnodes_type_over_de_missiontype():
    # DE says MT_CORRUPTION; /solnodes says "Void Flood". Neither is in the enum,
    # so both land on OTHER — but the node still resolves from the map.
    payload = {"ActiveMissions": [
        _mission(node="SolNode3", modifier="VoidT6", mt="MT_CORRUPTION"),
    ]}
    f = adapt_worldstate_fissures(payload, _NODE_MAP)[0]
    assert f.node == "Everview Arc"
    assert f.mission_type is MissionType.OTHER


def test_unknown_node_degrades_to_raw_id_and_de_mission_type():
    payload = {"ActiveMissions": [
        _mission(node="SolNode999", modifier="VoidT1", mt="MT_MOBILE_DEFENSE"),
    ]}
    f = adapt_worldstate_fissures(payload, _NODE_MAP)[0]
    assert f.node == "SolNode999" and f.planet == ""
    assert f.mission_type is MissionType.MOBILE_DEFENSE


def test_empty_document():
    assert adapt_worldstate_fissures({}, _NODE_MAP) == []
