"""Digital Extremes official worldState source — the authoritative live feed.

Used as the fissure fallback behind :class:`~titania.data.failover.FailoverDataSource`:
when the primary (warframestat) stalls, this pulls fissures straight from DE's
CDN at ``https://api.warframe.com/cdn/worldState.php``, which stays fresh
independently.

Node names come from ``/solnodes`` (static reference data) since DE's document
only carries ``SolNode`` ids. Non-fissure worldstate methods return empty
defaults: this source exists to keep *fissures* alive when the primary is down,
so the failover wrapper serves those other sections from whichever source does
answer. Wiring the full DE document (Baro inventory, alerts, invasions) through
here would be a much larger adaptation and isn't needed for that job.
"""

import asyncio
import json
import logging
import time
from functools import lru_cache
from importlib import resources
from typing import Any

import httpx

from titania.data.official.adapters import (
    adapt_archon_hunt,
    adapt_void_trader,
    adapt_worldstate_fissures,
    build_node_map,
)
from titania.domain.fissure import Fissure
from titania.domain.node import NodeInfo

log = logging.getLogger(__name__)

_RETRYABLE = (
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
)

# /solnodes is static reference data (changes only with a game update); cache it
# for the process rather than refetching per worldstate poll.
_NODE_MAP_TTL = 24 * 3600

# DE's CDN 403s empty/default user agents; present a browser-ish one.
_UA = "Mozilla/5.0 (compatible; TitaniaBot/1.0)"


@lru_cache(maxsize=1)
def _bundled_node_map() -> dict[str, tuple[str, str, str]]:
    """Offline SolNode->name/planet/type map bundled in the repo. Lets fissure
    node names resolve even when warframestat's ``/solnodes`` is unreachable (it
    lives on the same host we're failing over from). A snapshot of static
    reference data — refresh it from WFCD's ``solNodes.json`` on a game update."""
    raw = (
        resources.files("titania.data.official")
        .joinpath("solnodes_snapshot.json")
        .read_text(encoding="utf-8")
    )
    return build_node_map(json.loads(raw))


class OfficialWorldStateSource:
    """WarframeDataSource backed by DE's ``worldState.php`` (fissures only)."""

    def __init__(
        self,
        worldstate_url: str = "https://api.warframe.com/cdn/worldState.php",
        solnodes_base_url: str = "https://api.warframestat.us",
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
        max_attempts: int = 3,
    ) -> None:
        self._worldstate_url = worldstate_url
        self._solnodes_url = f"{solnodes_base_url.rstrip('/')}/solnodes"
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=timeout, headers={"User-Agent": _UA}
        )
        self._max_attempts = max_attempts

        self._node_map: dict[str, tuple[str, str, str]] | None = None
        self._node_map_at: float = 0.0
        self._node_map_lock = asyncio.Lock()

    async def _get_with_retry(
        self, url: str, *, params: dict[str, str] | None = None
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                return await self._client.get(url, params=params)
            except _RETRYABLE as e:
                last_exc = e
                if attempt < self._max_attempts - 1:
                    backoff = 0.5 * (2 ** attempt)
                    log.warning(
                        "official-worldstate %s attempt %d/%d failed (%s); retrying in %.1fs",
                        url, attempt + 1, self._max_attempts, type(e).__name__, backoff,
                    )
                    await asyncio.sleep(backoff)
        assert last_exc is not None
        raise last_exc

    async def _node_map_from_solnodes(self) -> dict[str, tuple[str, str, str]]:
        """``{node id: (name, planet, mission_type_raw)}`` for regular nodes."""
        resp = await self._get_with_retry(self._solnodes_url)
        resp.raise_for_status()
        return build_node_map(resp.json())

    async def _ensure_node_map(self) -> dict[str, tuple[str, str, str]]:
        now = time.monotonic()
        if self._node_map is not None and (now - self._node_map_at) < _NODE_MAP_TTL:
            return self._node_map
        async with self._node_map_lock:
            now = time.monotonic()
            if self._node_map is not None and (now - self._node_map_at) < _NODE_MAP_TTL:
                return self._node_map
            try:
                fresh = await self._node_map_from_solnodes()
            except (httpx.HTTPError, ValueError):
                # /solnodes lives on warframestat, which is the source we're
                # falling back *from* — so it's often down at the same time.
                # A missing node map must NOT kill the fissure list: use the
                # last-known map, else the bundled offline snapshot, so node
                # names still resolve. Don't stamp _node_map_at, so we retry
                # the live endpoint on the next call.
                fallback = self._node_map or _bundled_node_map()
                log.warning(
                    "node-map fetch from %s failed; serving fissures with "
                    "%s node names", self._solnodes_url,
                    "last-known" if self._node_map else "bundled-snapshot",
                )
                return fallback
            self._node_map = fresh
            self._node_map_at = time.monotonic()
            return self._node_map

    async def fetch_fissures(self) -> list[Fissure]:
        node_map = await self._ensure_node_map()
        resp = await self._get_with_retry(self._worldstate_url)
        resp.raise_for_status()
        return adapt_worldstate_fissures(resp.json(), node_map)

    async def fetch_node_catalog(self) -> frozenset[str]:
        node_map = await self._ensure_node_map()
        return frozenset(name for name, _planet, _type in node_map.values() if name)

    async def fetch_node_details(self) -> dict[str, NodeInfo]:
        node_map = await self._ensure_node_map()
        return {
            name: NodeInfo(name=name, planet=planet, mission_type_raw=type_raw)
            for name, planet, type_raw in node_map.values()
            if name
        }

    async def fetch_void_trader(self) -> dict[str, Any]:
        # Baro summary failover: the window + relay are exact; inventory item
        # names are approximate (DE ships Lotus paths, not friendly names).
        resp = await self._get_with_retry(self._worldstate_url)
        resp.raise_for_status()
        return adapt_void_trader(resp.json())

    async def fetch_archon_hunt(self) -> dict[str, Any]:
        resp = await self._get_with_retry(self._worldstate_url)
        resp.raise_for_status()
        return adapt_archon_hunt(resp.json())

    # Not adapted from DE (Lotus-path rewards / missing schedule); the failover
    # wrapper serves these from whichever source answers.
    async def fetch_alerts(self) -> list[dict[str, Any]]:
        return []

    async def fetch_invasions(self) -> list[dict[str, Any]]:
        return []

    async def fetch_calendar(self) -> dict[str, Any]:
        return {}

    async def fetch_vault_trader(self) -> dict[str, Any]:
        return {}

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "OfficialWorldStateSource":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
