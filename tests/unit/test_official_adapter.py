from datetime import datetime, timedelta, timezone

from titania.data.official.adapters import adapt_worldstate_fissures, build_node_map
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


def test_build_node_map_includes_phobos_settlement_nodes():
    # DE references Phobos fissures by their historical SettlementNode* ids;
    # the map must resolve those, not just SolNode*, or they render as raw ids.
    payload = {
        "SolNode1": {"value": "Hepit (Void)", "type": "Capture"},
        "SettlementNode2": {"value": "Skyresh (Phobos)", "type": "Capture"},
        "CrewBattleNode1": {"value": "Gian Point (Earth Proxima)", "type": "Skirmish"},
        "MercuryHUB": {"value": "Larunda Relay (Mercury)"},
        "PvpNode1": {"value": "Cephalon Capture (Ceres)", "type": "Capture"},
    }
    node_map = build_node_map(payload)
    assert node_map["SolNode1"] == ("Hepit", "Void", "Capture")
    assert node_map["SettlementNode2"] == ("Skyresh", "Phobos", "Capture")
    # Non-mission node keys (relays, PvP, railjack) are excluded.
    assert "MercuryHUB" not in node_map
    assert "PvpNode1" not in node_map
    assert "CrewBattleNode1" not in node_map


def test_settlement_node_resolves_in_fissure_adapt():
    node_map = {"SettlementNode2": ("Skyresh", "Phobos", "Capture")}
    payload = {"ActiveMissions": [_mission(node="SettlementNode2", modifier="VoidT2")]}
    f = adapt_worldstate_fissures(payload, node_map)[0]
    assert f.node == "Skyresh" and f.planet == "Phobos"
    assert f.mission_type is MissionType.CAPTURE


# --- vendor adapters ---------------------------------------------------------
from titania.data.official.adapters import (  # noqa: E402
    adapt_archon_hunt,
    adapt_void_trader,
)
from titania.domain.vendors import resolve_archon  # noqa: E402


def _ms_of(dt):
    return {"$date": {"$numberLong": str(int(dt.timestamp() * 1000))}}


def test_adapt_archon_hunt_boss_resolves():
    payload = {"LiteSorties": [{"Boss": "SORTIE_BOSS_AMAR"}]}
    out = adapt_archon_hunt(payload)
    assert out == {"boss": "SORTIE_BOSS_AMAR"}
    # The boss enum resolves through the existing shard mapping unchanged.
    assert resolve_archon(out["boss"]).color == "red"


def test_adapt_archon_hunt_empty_when_missing():
    assert adapt_archon_hunt({}) == {}
    assert adapt_archon_hunt({"LiteSorties": []}) == {}


def test_adapt_void_trader_present_with_manifest():
    now = datetime.now(timezone.utc)
    payload = {"VoidTraders": [{
        "Character": "Baro'Ki Teel", "Node": "MercuryHUB",
        "Activation": _ms_of(now - timedelta(hours=1)),
        "Expiry": _ms_of(now + timedelta(days=1)),
        "Manifest": [
            {"ItemType": "/Lotus/Types/StoreItems/Packages/MegaPrimeVault/MPVBansheePrimeSinglePack", "PrimePrice": 6},
            {"ItemType": "/Lotus/StoreItems/Powersuits/Banshee/BansheePrime", "PrimePrice": 3},
        ],
    }]}
    vt = adapt_void_trader(payload)
    assert vt["location"] == "Larunda Relay (Mercury)"
    assert vt["character"] == "Baro Ki'Teer"
    assert len(vt["inventory"]) == 2  # non-empty => VoidTraderState.is_present
    assert vt["inventory"][1] == {"item": "Banshee Prime", "ducats": 3}


def test_adapt_void_trader_absent_has_empty_inventory():
    now = datetime.now(timezone.utc)
    payload = {"VoidTraders": [{
        "Node": "PlutoHUB",
        "Activation": _ms_of(now + timedelta(days=3)),
        "Expiry": _ms_of(now + timedelta(days=5)),
        # No Manifest while Baro is away.
    }]}
    vt = adapt_void_trader(payload)
    assert vt["location"] == "Orcus Relay (Pluto)"
    assert vt["inventory"] == []  # => is_present False => "arrives" line


def test_adapt_void_trader_empty_when_missing():
    assert adapt_void_trader({}) == {}
