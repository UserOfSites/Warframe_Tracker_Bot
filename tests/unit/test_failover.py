from datetime import datetime, timedelta, timezone

from titania.data.failover import FailoverDataSource
from titania.domain.era import Era
from titania.domain.fissure import Fissure
from titania.domain.mission_type import MissionType
from titania.domain.node import NodeInfo


def _fissure(node="Hepit", era=Era.LITH):
    return Fissure(
        era=era, mission_type=MissionType.CAPTURE, node=node, planet="Void",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        is_steel_path=False, is_hard=False, tier=1,
    )


def _railjack():
    return _fissure(node="Gian Point")  # Proxima node -> is_railjack


class _Src:
    """Configurable fake source. Any fetch raises RuntimeError when down=True."""

    def __init__(self, *, fissures=None, down=False, calendar=None):
        self._fissures = fissures or []
        self._calendar = calendar or {}
        self.down = down
        self.fissure_calls = 0
        self.calendar_calls = 0
        self.closed = False

    def _guard(self):
        if self.down:
            raise RuntimeError("upstream down")

    async def fetch_fissures(self):
        self.fissure_calls += 1
        self._guard()
        return list(self._fissures)

    async def fetch_node_catalog(self):
        self._guard()
        return frozenset({"Hepit"})

    async def fetch_node_details(self):
        self._guard()
        return {"Hepit": NodeInfo(name="Hepit", planet="Void", mission_type_raw="Capture")}

    async def fetch_void_trader(self):
        self._guard()
        return {"inventory": []}

    async def fetch_archon_hunt(self):
        self._guard()
        return {"boss": "Nira"}

    async def fetch_alerts(self):
        self._guard()
        return [{"id": "a"}]

    async def fetch_invasions(self):
        self._guard()
        return [{"id": "i"}]

    async def fetch_calendar(self):
        self.calendar_calls += 1
        self._guard()
        return self._calendar

    async def fetch_vault_trader(self):
        self._guard()
        return {"schedule": []}

    async def aclose(self):
        self.closed = True


def _failover(primary, fallback, **kw):
    return FailoverDataSource([("primary", primary), ("fallback", fallback)], **kw)


# --- fissures ---------------------------------------------------------------
async def test_fissures_prefer_primary_when_healthy():
    fds = _failover(_Src(fissures=[_fissure("Ukko")]), _Src(fissures=[_fissure("Hepit")]))
    assert [f.node for f in await fds.fetch_fissures()] == ["Ukko"]


async def test_fissures_failover_when_primary_raises():
    fds = _failover(_Src(down=True), _Src(fissures=[_fissure("Hepit")]))
    assert [f.node for f in await fds.fetch_fissures()] == ["Hepit"]


async def test_fissures_failover_when_primary_degraded():
    # Primary answers 200 but with fewer *usable* fissures (mostly Railjack).
    primary = _Src(fissures=[_railjack(), _railjack(), _fissure("Hepit")])  # 1 usable
    fallback = _Src(fissures=[_fissure("A"), _fissure("B"), _fissure("C")])  # 3 usable
    fds = _failover(primary, fallback)
    assert {f.node for f in await fds.fetch_fissures()} == {"A", "B", "C"}


async def test_fissures_empty_from_all():
    fds = _failover(_Src(down=True), _Src(down=True))
    assert await fds.fetch_fissures() == []


# --- health / cooldown ------------------------------------------------------
async def test_unhealthy_source_is_skipped_until_cooldown():
    primary = _Src(down=True)
    fallback = _Src(fissures=[_fissure("Hepit")])
    fds = _failover(primary, fallback, cooldown_seconds=1000)

    await fds.fetch_fissures()          # primary raises -> marked unhealthy
    assert primary.fissure_calls == 1
    await fds.fetch_fissures()          # primary in cooldown -> skipped
    await fds.fetch_fissures()
    assert primary.fissure_calls == 1   # never retried while cooling down
    assert fallback.fissure_calls == 3


async def test_source_reprobed_after_cooldown_and_recovers():
    primary = _Src(down=True)
    fallback = _Src(fissures=[_fissure("Hepit")])
    fds = _failover(primary, fallback, cooldown_seconds=1000)
    await fds.fetch_fissures()
    assert fds._active == "fallback"

    # Cooldown elapses and the primary is back.
    fds._unhealthy_until["primary"] = 0.0
    primary.down = False
    primary._fissures = [_fissure("Ukko")]
    assert [f.node for f in await fds.fetch_fissures()] == ["Ukko"]
    assert fds._active == "primary"
    assert "primary" not in fds._unhealthy_until  # healthy again


# --- non-fissure methods ----------------------------------------------------
async def test_non_fissure_failover_to_next_source():
    primary = _Src(down=True)
    fallback = _Src(calendar={"season": "Winter"})
    fds = _failover(primary, fallback)
    assert await fds.fetch_calendar() == {"season": "Winter"}
    assert await fds.fetch_alerts() == [{"id": "a"}]


async def test_non_fissure_empty_answer_does_not_trigger_failover():
    # Primary succeeds but returns an empty calendar — that's a valid answer,
    # so the fallback must NOT be consulted.
    primary = _Src(calendar={})
    fallback = _Src(calendar={"season": "SHOULD_NOT_APPEAR"})
    fds = _failover(primary, fallback)
    assert await fds.fetch_calendar() == {}
    assert fallback.calendar_calls == 0


async def test_non_fissure_default_when_all_down():
    fds = _failover(_Src(down=True), _Src(down=True))
    assert await fds.fetch_alerts() == []
    assert await fds.fetch_void_trader() == {}
    assert await fds.fetch_node_catalog() == frozenset()


async def test_aclose_closes_every_source():
    primary, fallback = _Src(), _Src()
    await _failover(primary, fallback).aclose()
    assert primary.closed and fallback.closed


def test_requires_at_least_one_source():
    import pytest
    with pytest.raises(ValueError):
        FailoverDataSource([])
