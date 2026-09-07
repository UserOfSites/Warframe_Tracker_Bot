from datetime import datetime, timedelta, timezone

import httpx

from titania.data.official.source import OfficialWorldStateSource


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


async def test_node_map_falls_back_to_bundled_snapshot_when_solnodes_down(monkeypatch):
    src = OfficialWorldStateSource()
    try:
        async def boom():
            raise httpx.ConnectError("down")

        monkeypatch.setattr(src, "_node_map_from_solnodes", boom)
        # No last-known map, and crucially no exception: the bundled offline
        # snapshot is used so names still resolve.
        node_map = await src._ensure_node_map()
        assert len(node_map) > 100  # snapshot has a few hundred nodes
        assert node_map["SolNode122"] == ("Stephano", "Uranus", "Defense")
    finally:
        await src.aclose()


async def test_node_map_reuses_last_known_on_later_failure(monkeypatch):
    src = OfficialWorldStateSource()
    try:
        calls = {"n": 0}

        async def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                return {"SolNode1": ("Hepit", "Void", "Capture")}
            raise httpx.ConnectError("down")

        monkeypatch.setattr(src, "_node_map_from_solnodes", flaky)
        first = await src._ensure_node_map()
        assert first == {"SolNode1": ("Hepit", "Void", "Capture")}
        # Force the cache to look stale so the next call refetches (and fails).
        src._node_map_at = 0.0
        assert await src._ensure_node_map() == first  # last-known reused
    finally:
        await src.aclose()


async def test_fetch_fissures_survives_solnodes_outage(monkeypatch):
    src = OfficialWorldStateSource()
    try:
        async def boom():
            raise httpx.ConnectError("down")

        monkeypatch.setattr(src, "_node_map_from_solnodes", boom)

        expiry_ms = str(int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp() * 1000))
        worldstate = {"ActiveMissions": [{
            "Node": "SolNode122", "Modifier": "VoidT3", "MissionType": "MT_DEFENSE",
            "Hard": True, "Expiry": {"$date": {"$numberLong": expiry_ms}},
        }]}

        async def fake_get(url, **kwargs):
            return _Resp(worldstate)

        monkeypatch.setattr(src, "_get_with_retry", fake_get)

        fissures = await src.fetch_fissures()
        assert len(fissures) == 1
        f = fissures[0]
        # Name still resolves from the bundled snapshot even with /solnodes down.
        assert f.node == "Stephano" and f.planet == "Uranus"
        assert f.mission_type.value == "Defense"
        assert f.era.value == "Neo"
        assert f.is_steel_path is True
    finally:
        await src.aclose()
