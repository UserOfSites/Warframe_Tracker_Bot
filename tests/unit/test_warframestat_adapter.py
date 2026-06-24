from datetime import datetime, timezone

from titania.data.warframestat.adapters import adapt_fissure, adapt_fissures
from titania.domain.era import Era
from titania.domain.mission_type import MissionType


def _raw(**overrides):
    base = {
        "node": "Augustus (Mars)",
        "tier": "Lith",
        "tierNum": 1,
        "missionType": "Excavation",
        "expiry": "2099-01-01T01:00:00Z",
        "isHard": False,
        "isStorm": False,
        "expired": False,
    }
    base.update(overrides)
    return base


def test_adapter_splits_node_and_planet():
    f = adapt_fissure(_raw())
    assert f.node == "Augustus"
    assert f.planet == "Mars"


def test_adapter_parses_era_and_mission_type():
    f = adapt_fissure(_raw(tier="Neo", missionType="Exterminate"))
    assert f.era == Era.NEO
    assert f.mission_type == MissionType.EXTERMINATE


def test_adapter_parses_expiry_as_utc():
    f = adapt_fissure(_raw(expiry="2099-01-01T01:00:00Z"))
    assert f.expires_at == datetime(2099, 1, 1, 1, 0, 0, tzinfo=timezone.utc)


def test_adapter_flags_steel_path_from_isHard():
    sp = adapt_fissure(_raw(isHard=True))
    normal = adapt_fissure(_raw(isHard=False))
    assert sp.is_steel_path is True
    assert normal.is_steel_path is False


def test_adapter_unknown_mission_type_falls_back_to_other():
    f = adapt_fissure(_raw(missionType="WhateverNewMode"))
    assert f.mission_type == MissionType.OTHER


def test_adapt_fissures_skips_expired_and_malformed():
    payload = [
        _raw(),
        _raw(expired=True),
        {"node": "broken"},  # missing required fields
    ]
    out = adapt_fissures(payload)
    assert len(out) == 1
