import asyncio
from datetime import datetime, timezone

from titania.data.cached import CachedDataSource
from titania.domain.era import Era
from titania.domain.fissure import Fissure
from titania.domain.mission_type import MissionType


class _StubSource:
    def __init__(self) -> None:
        self.calls = 0
        self.node_calls = 0

    async def fetch_fissures(self) -> list[Fissure]:
        self.calls += 1
        return [
            Fissure(
                era=Era.LITH,
                mission_type=MissionType.CAPTURE,
                node="Hepit",
                planet="Void",
                expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
                is_steel_path=False,
                is_hard=False,
                tier=1,
            )
        ]

    async def fetch_node_catalog(self) -> frozenset[str]:
        self.node_calls += 1
        return frozenset({"Hepit", "Ukko"})

    async def fetch_void_trader(self) -> dict:
        return {"inventory": []}

    async def aclose(self) -> None:
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


async def test_cache_serves_from_memory_within_ttl():
    stub = _StubSource()
    cache = CachedDataSource(stub, ttl_seconds=60)
    await cache.fetch_fissures()
    await cache.fetch_fissures()
    await cache.fetch_fissures()
    assert stub.calls == 1


async def test_cache_refreshes_after_ttl_expires():
    stub = _StubSource()
    cache = CachedDataSource(stub, ttl_seconds=0)  # immediately expires
    await cache.fetch_fissures()
    await cache.fetch_fissures()
    assert stub.calls == 2


async def test_concurrent_callers_share_a_single_upstream_call():
    stub = _StubSource()
    cache = CachedDataSource(stub, ttl_seconds=60)
    await asyncio.gather(*(cache.fetch_fissures() for _ in range(10)))
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
    # Stub returns {"inventory": []} — confirm we got it.
    assert payload == {"inventory": []}
