import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from titania.data.source import WarframeDataSource
from titania.domain.fissure import Fissure
from titania.domain.node import NodeInfo


class CachedDataSource:
    """Wraps any WarframeDataSource with a cache whose validity is tied to
    when the data *actually* changes upstream — not a fixed TTL.

    - **Fissures** rotate when their ``expires_at`` passes. We cache the list
      until the earliest fissure expires; on the next call after that we
      refetch. Result: the refresher loop can tick every 30s for the embed
      timer (now a native ``<t:..:R>``, updated client-side) without flooding
      ``api.warframestat.us``.
    - **Void trader** has a single relevant transition per cached state:
      either "Baro arrives" (``activation``) or "Baro leaves" (``expiry``).
      Cache until that.
    - **Node catalog / details** only change with a Warframe update — long-
      lived cache, unchanged from before.
    """

    _NODE_CATALOG_TTL = 24 * 3600  # 24h

    def __init__(self, inner: WarframeDataSource, ttl_seconds: float) -> None:
        self._inner = inner
        # Fallback for the rare case where a fresh fetch returns nothing usable
        # (e.g. fissure list empty, void_trader payload missing timestamps).
        self._fallback = timedelta(seconds=max(ttl_seconds, 30))

        self._fissures: list[Fissure] | None = None
        self._fissures_valid_until: datetime | None = None
        self._fissures_lock = asyncio.Lock()

        self._nodes: frozenset[str] | None = None
        self._nodes_loaded_at: float = 0.0
        self._nodes_lock = asyncio.Lock()

        self._node_details: dict[str, NodeInfo] | None = None
        self._node_details_loaded_at: float = 0.0
        self._node_details_lock = asyncio.Lock()

        self._void_trader: dict[str, Any] | None = None
        self._void_trader_valid_until: datetime | None = None
        self._void_trader_lock = asyncio.Lock()

    async def fetch_fissures(self) -> list[Fissure]:
        now = datetime.now(timezone.utc)
        if (
            self._fissures is not None
            and self._fissures_valid_until is not None
            and now < self._fissures_valid_until
        ):
            return list(self._fissures)
        async with self._fissures_lock:
            now = datetime.now(timezone.utc)
            if (
                self._fissures is not None
                and self._fissures_valid_until is not None
                and now < self._fissures_valid_until
            ):
                return list(self._fissures)
            fresh = await self._inner.fetch_fissures()
            self._fissures = fresh
            if fresh:
                self._fissures_valid_until = min(f.expires_at for f in fresh)
            else:
                # Empty list — fall back to the configured TTL so we don't
                # hammer the upstream on a transient outage.
                self._fissures_valid_until = now + self._fallback
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
        now = datetime.now(timezone.utc)
        if (
            self._void_trader is not None
            and self._void_trader_valid_until is not None
            and now < self._void_trader_valid_until
        ):
            return dict(self._void_trader)
        async with self._void_trader_lock:
            now = datetime.now(timezone.utc)
            if (
                self._void_trader is not None
                and self._void_trader_valid_until is not None
                and now < self._void_trader_valid_until
            ):
                return dict(self._void_trader)
            fresh = await self._inner.fetch_void_trader()
            self._void_trader = fresh
            self._void_trader_valid_until = (
                self._next_void_trader_transition(fresh, now)
                or now + self._fallback
            )
            return dict(fresh)

    def _next_void_trader_transition(
        self, payload: dict[str, Any], now: datetime
    ) -> datetime | None:
        """The next ``activation`` or ``expiry`` strictly in the future. Baro
        has at most one of these pending: if absent, the soonest is
        ``activation`` (arrival); if present, it's ``expiry`` (departure)."""
        candidates: list[datetime] = []
        for key in ("activation", "expiry"):
            raw = payload.get(key)
            if not isinstance(raw, str):
                continue
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
            except (ValueError, AttributeError):
                continue
            if dt > now:
                candidates.append(dt)
        return min(candidates) if candidates else None

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def __aenter__(self) -> "CachedDataSource":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
