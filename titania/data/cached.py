import asyncio
import time
from typing import Any

from titania.data.source import WarframeDataSource
from titania.domain.fissure import Fissure
from titania.domain.node import NodeInfo


class CachedDataSource:
    """Wraps any WarframeDataSource with a TTL cache for fissure data and a
    long-lived cache for the node catalog.

    - Fissures rotate fast; the cache amortizes the upstream call across all
      guilds. Global, not per-guild — filtering happens above this layer.
    - Node catalog only changes on a new Warframe update (rare); cache once
      per process lifetime.
    """

    _NODE_CATALOG_TTL = 24 * 3600  # 24h

    def __init__(self, inner: WarframeDataSource, ttl_seconds: float) -> None:
        self._inner = inner
        self._ttl = ttl_seconds
        self._fissures: list[Fissure] | None = None
        self._fissures_loaded_at: float = 0.0
        self._nodes: frozenset[str] | None = None
        self._nodes_loaded_at: float = 0.0
        self._node_details: dict[str, NodeInfo] | None = None
        self._node_details_loaded_at: float = 0.0
        self._fissures_lock = asyncio.Lock()
        self._nodes_lock = asyncio.Lock()
        self._node_details_lock = asyncio.Lock()

    async def fetch_fissures(self) -> list[Fissure]:
        now = time.monotonic()
        if self._fissures is not None and (now - self._fissures_loaded_at) < self._ttl:
            return list(self._fissures)
        async with self._fissures_lock:
            now = time.monotonic()
            if self._fissures is not None and (now - self._fissures_loaded_at) < self._ttl:
                return list(self._fissures)
            fresh = await self._inner.fetch_fissures()
            self._fissures = fresh
            self._fissures_loaded_at = time.monotonic()
            return list(fresh)

    async def fetch_node_catalog(self) -> frozenset[str]:
        now = time.monotonic()
        if self._nodes is not None and (now - self._nodes_loaded_at) < self._NODE_CATALOG_TTL:
            return self._nodes
        async with self._nodes_lock:
            now = time.monotonic()
            if self._nodes is not None and (now - self._nodes_loaded_at) < self._NODE_CATALOG_TTL:
                return self._nodes
            self._nodes = await self._inner.fetch_node_catalog()
            self._nodes_loaded_at = time.monotonic()
            return self._nodes

    async def fetch_node_details(self) -> dict[str, NodeInfo]:
        now = time.monotonic()
        if (
            self._node_details is not None
            and (now - self._node_details_loaded_at) < self._NODE_CATALOG_TTL
        ):
            return dict(self._node_details)
        async with self._node_details_lock:
            now = time.monotonic()
            if (
                self._node_details is not None
                and (now - self._node_details_loaded_at) < self._NODE_CATALOG_TTL
            ):
                return dict(self._node_details)
            self._node_details = await self._inner.fetch_node_details()
            self._node_details_loaded_at = time.monotonic()
            return dict(self._node_details)

    async def fetch_void_trader(self) -> dict[str, Any]:
        # Delegated as-is — BaroService's per-visit cache already protects
        # the wiki call. Void trader payload is small (~300 bytes) so a
        # second-tier cache here would be wasted complexity.
        return await self._inner.fetch_void_trader()

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def __aenter__(self) -> "CachedDataSource":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
