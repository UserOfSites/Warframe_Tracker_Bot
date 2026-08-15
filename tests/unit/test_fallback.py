from datetime import datetime, timedelta, timezone

from titania.data.fallback import FallbackDataSource
from titania.domain.era import Era
from titania.domain.fissure import Fissure
from titania.domain.mission_type import MissionType
from titania.domain.node import NodeInfo


def _fissure(node="Hepit", era=Era.LITH, mission_type=MissionType.CAPTURE):
    return Fissure(
        era=era, mission_type=mission_type, node=node, planet="Void",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        is_steel_path=False, is_hard=False, tier=1,
    )


def _railjack():
    # "Gian Point" is a Proxima node -> is_railjack() true regardless of type.
    return _fissure(node="Gian Point")


class _Src:
    def __init__(self, fissures=None, raise_on_fissures=False):
        self._fissures = fissures or []
        self._raise = raise_on_fissures
        self.fissure_calls = 0
        self.other_calls = 0
        self.closed = False

    async def fetch_fissures(self):
        self.fissure_calls += 1
        if self._raise:
            raise RuntimeError("boom")
        return list(self._fissures)

    async def fetch_node_catalog(self):
        self.other_calls += 1
        return frozenset({"Hepit"})

    async def fetch_node_details(self):
        self.other_calls += 1
        return {"Hepit": NodeInfo(name="Hepit", planet="Void", mission_type_raw="Capture")}

    async def fetch_void_trader(self):
        self.other_calls += 1
        return {"inventory": []}

    async def fetch_archon_hunt(self):
        self.other_calls += 1
        return {"boss": "Nira"}

    async def fetch_alerts(self):
        self.other_calls += 1
        return [{"id": "a"}]

    async def fetch_invasions(self):
        self.other_calls += 1
        return [{"id": "i"}]

    async def aclose(self):
        self.closed = True


async def test_uses_primary_when_it_is_healthy():
    primary = _Src(fissures=[_fissure("Ukko"), _fissure("Taranis")])
    fallback = _Src(fissures=[_fissure("Hepit"), _fissure("Taranis")])
    fds = FallbackDataSource(primary, fallback)
    out = await fds.fetch_fissures()
    assert {f.node for f in out} == {"Ukko", "Taranis"}  # primary served (tie -> primary)
    assert fds._on_fallback is False


async def test_falls_back_when_primary_empty():
    primary = _Src(fissures=[])           # stalled -> empty after adapter drop
    fallback = _Src(fissures=[_fissure("Hepit")])
    fds = FallbackDataSource(primary, fallback)
    out = await fds.fetch_fissures()
    assert [f.node for f in out] == ["Hepit"]
    assert fds._on_fallback is True


async def test_falls_back_when_primary_is_degraded_partial_list():
    """The live failure: primary returns a few fissures, mostly Railjack, so it
    has fewer *usable* ones than the complete fallback."""
    primary = _Src(fissures=[_railjack(), _railjack(), _fissure("Hepit")])  # 1 usable
    fallback = _Src(fissures=[_fissure("Hepit"), _fissure("Ukko"), _fissure("Taranis")])  # 3
    fds = FallbackDataSource(primary, fallback)
    out = await fds.fetch_fissures()
    assert {f.node for f in out} == {"Hepit", "Ukko", "Taranis"}
    assert fds._on_fallback is True


async def test_requiem_does_not_count_as_usable():
    # Primary's only non-railjack fissure is Requiem (never rendered), so it has
    # zero usable and loses to a fallback with a real one.
    primary = _Src(fissures=[_fissure("Kelpie", era=Era.REQUIEM)])
    fallback = _Src(fissures=[_fissure("Hepit")])
    fds = FallbackDataSource(primary, fallback)
    out = await fds.fetch_fissures()
    assert [f.node for f in out] == ["Hepit"]


async def test_falls_back_when_primary_raises():
    primary = _Src(raise_on_fissures=True)
    fallback = _Src(fissures=[_fissure("Hepit")])
    fds = FallbackDataSource(primary, fallback)
    out = await fds.fetch_fissures()
    assert [f.node for f in out] == ["Hepit"]


async def test_switches_back_when_primary_recovers():
    primary = _Src(fissures=[])
    fallback = _Src(fissures=[_fissure("Hepit")])
    fds = FallbackDataSource(primary, fallback)
    await fds.fetch_fissures()
    assert fds._on_fallback is True
    # Primary comes back to full health (more usable than fallback).
    primary._fissures = [_fissure("Ukko"), _fissure("Taranis")]
    out = await fds.fetch_fissures()
    assert {f.node for f in out} == {"Ukko", "Taranis"}
    assert fds._on_fallback is False


async def test_empty_from_both_returns_empty():
    fds = FallbackDataSource(_Src(fissures=[]), _Src(fissures=[]))
    assert await fds.fetch_fissures() == []


async def test_other_methods_delegate_to_primary_only():
    primary = _Src(fissures=[])
    fallback = _Src(fissures=[_fissure("Hepit")])
    fds = FallbackDataSource(primary, fallback)
    assert await fds.fetch_void_trader() == {"inventory": []}
    assert await fds.fetch_archon_hunt() == {"boss": "Nira"}
    assert await fds.fetch_alerts() == [{"id": "a"}]
    assert await fds.fetch_invasions() == [{"id": "i"}]
    assert await fds.fetch_node_catalog() == frozenset({"Hepit"})
    await fds.fetch_node_details()
    assert fallback.other_calls == 0  # fallback is fissures-only


async def test_aclose_closes_both():
    primary, fallback = _Src(), _Src()
    await FallbackDataSource(primary, fallback).aclose()
    assert primary.closed and fallback.closed
