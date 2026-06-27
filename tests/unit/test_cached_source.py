import asyncio
from datetime import datetime, timedelta, timezone

from titania.data.cached import CachedDataSource
from titania.domain.era import Era
from titania.domain.fissure import Fissure
from titania.domain.mission_type import MissionType


class _StubSource:
    def __init__(self, *, expires_in: timedelta = timedelta(hours=1)) -> None:
        self.calls = 0
        self.node_calls = 0
        self._expires_in = expires_in

    async def fetch_fissures(self) -> list[Fissure]:
        self.calls += 1
        # Anchor at fetch-time so the cache validity tracks "now".
        return [
            Fissure(
                era=Era.LITH,
                mission_type=MissionType.CAPTURE,
                node="Hepit",
                planet="Void",
                expires_at=datetime.now(timezone.utc) + self._expires_in,
                is_steel_path=False,
                is_hard=False,
                tier=1,
            )
        ]

    async def fetch_node_catalog(self) -> frozenset[str]:
        self.node_calls += 1
        return frozenset({"Hepit", "Ukko"})

    async def fetch_node_details(self) -> dict:
        from titania.domain.node import NodeInfo
        return {
            "Hepit": NodeInfo(name="Hepit", planet="Void", mission_type_raw="Capture"),
            "Ukko":  NodeInfo(name="Ukko",  planet="Void", mission_type_raw="Capture"),
        }

    async def fetch_void_trader(self) -> dict:
        return {"inventory": []}

    async def aclose(self) -> None:
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


async def test_cache_serves_from_memory_until_earliest_expiry():
    """Cache is valid while the soonest-expiring fissure hasn't expired yet."""
    stub = _StubSource(expires_in=timedelta(hours=1))
    cache = CachedDataSource(stub, ttl_seconds=60)
    for _ in range(3):
        await cache.fetch_fissures()
    assert stub.calls == 1


async def test_cache_refetches_after_earliest_fissure_expires():
    """Once the soonest-expiring fissure passes its expiry, the next call
    refetches from upstream (each upstream call returns a fresh window that
    is already in the past, so subsequent calls keep refetching — exactly
    the right behaviour while the fissure list is rotating)."""
    stub = _StubSource(expires_in=timedelta(seconds=-10))  # already past
    cache = CachedDataSource(stub, ttl_seconds=60)
    await cache.fetch_fissures()
    await cache.fetch_fissures()
    assert stub.calls == 2


async def test_concurrent_callers_share_a_single_upstream_call():
    stub = _StubSource(expires_in=timedelta(hours=1))
    cache = CachedDataSource(stub, ttl_seconds=60)
    await asyncio.gather(*(cache.fetch_fissures() for _ in range(10)))
    assert stub.calls == 1


async def test_empty_fissure_list_falls_back_to_configured_ttl():
    """If upstream returns nothing usable, we don't have an expiry to anchor
    to — fall back to the configured TTL so we don't hammer the API."""
    class _Empty(_StubSource):
        async def fetch_fissures(self) -> list[Fissure]:
            self.calls += 1
            return []
    stub = _Empty()
    cache = CachedDataSource(stub, ttl_seconds=60)
    await cache.fetch_fissures()
    await cache.fetch_fissures()
    # Fallback TTL still applies — second call is cached.
    assert stub.calls == 1


async def test_node_catalog_cached_for_process_lifetime():
    stub = _StubSource()
    cache = CachedDataSource(stub, ttl_seconds=60)
    for _ in range(5):
        await cache.fetch_node_catalog()
    assert stub.node_calls == 1


def test_cached_source_implements_full_datasource_protocol():
    """Every method on WarframeDataSource must exist on the decorator. If we
    grow the Protocol with a new method, this test fails until the decorator
    is updated (catches the AttributeError-at-runtime bug class)."""
    from titania.data.source import WarframeDataSource

    # Pick up Protocol methods that aren't dunder/private.
    protocol_methods = {
        name
        for name in dir(WarframeDataSource)
        if not name.startswith("_") and callable(getattr(WarframeDataSource, name, None))
    }
    cached_methods = {
        name
        for name in dir(CachedDataSource)
        if not name.startswith("_") and callable(getattr(CachedDataSource, name, None))
    }
    missing = protocol_methods - cached_methods
    assert not missing, f"CachedDataSource missing forwards for: {sorted(missing)}"


async def test_cached_source_forwards_fetch_void_trader():
    stub = _StubSource()
    cache = CachedDataSource(stub, ttl_seconds=60)
    payload = await cache.fetch_void_trader()
    assert payload == {"inventory": []}


async def test_void_trader_cached_until_next_transition():
    """When the payload has an upcoming activation/expiry, the cache stays
    valid until that timestamp — no per-tick refetch."""
    near_future = datetime.now(timezone.utc) + timedelta(hours=2)

    class _BaroStub(_StubSource):
        def __init__(self):
            super().__init__()
            self.vt_calls = 0
        async def fetch_void_trader(self):
            self.vt_calls += 1
            return {
                "activation": near_future.isoformat().replace("+00:00", "Z"),
                "expiry":     (near_future + timedelta(days=2)).isoformat().replace("+00:00", "Z"),
                "inventory":  [],
            }

    stub = _BaroStub()
    cache = CachedDataSource(stub, ttl_seconds=60)
    for _ in range(5):
        await cache.fetch_void_trader()
    assert stub.vt_calls == 1


async def test_void_trader_refetches_after_transition_passes():
    """A payload whose activation+expiry are both in the past has no future
    transition — we fall back to the configured TTL rather than caching
    forever on stale data."""
    past = datetime.now(timezone.utc) - timedelta(days=1)

    class _BaroStub(_StubSource):
        def __init__(self):
            super().__init__()
            self.vt_calls = 0
        async def fetch_void_trader(self):
            self.vt_calls += 1
            return {
                "activation": past.isoformat().replace("+00:00", "Z"),
                "expiry":     past.isoformat().replace("+00:00", "Z"),
                "inventory":  [],
            }

    stub = _BaroStub()
    # ttl_seconds is clamped to a 30s floor inside the cache; fine for the
    # single-call assertion below.
    cache = CachedDataSource(stub, ttl_seconds=60)
    await cache.fetch_void_trader()
    await cache.fetch_void_trader()
    # First call refetched (no cache); second served from the fallback TTL.
    assert stub.vt_calls == 1
