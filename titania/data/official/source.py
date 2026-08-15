"""Digital Extremes official worldState source — the authoritative live feed.

Used as the fissure *fallback* behind :class:`FallbackDataSource`: when the
primary (warframestat) stalls, this pulls fissures straight from DE's CDN at
``https://api.warframe.com/cdn/worldState.php``, which stays fresh independently.

Node names come from ``/solnodes`` (static reference data) since DE's document
only carries ``SolNode`` ids. Non-fissure worldstate methods return empty
defaults: this source exists to keep *fissures* alive when the primary is down,
and the fallback wrapper serves every other section from the primary. Wiring the
full DE document (Baro inventory, alerts, invasions) through here would be a
much larger adaptation and isn't needed for that job.
"""

import asyncio
import logging
import time
from typing import Any

import httpx

from titania.data.official.adapters import adapt_worldstate_fissures
from titania.data.warframestat.source import _split_node_value
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
        """``{SolNode id: (name, planet, mission_type_raw)}`` for regular nodes."""
        resp = await self._get_with_retry(self._solnodes_url)
        resp.raise_for_status()
        payload = resp.json()
        out: dict[str, tuple[str, str, str]] = {}
        for key, entry in payload.items():
            if not (key.startswith("SolNode") and isinstance(entry, dict)):
                continue
            value = entry.get("value")
            if not (isinstance(value, str) and "(" in value):
                continue
            name, planet = _split_node_value(value)
            mt_raw = entry.get("type")
            out[key] = (name, planet, mt_raw if isinstance(mt_raw, str) else "")
        return out

    async def _ensure_node_map(self) -> dict[str, tuple[str, str, str]]:
        now = time.monotonic()
        if self._node_map is not None and (now - self._node_map_at) < _NODE_MAP_TTL:
            return self._node_map
        async with self._node_map_lock:
            now = time.monotonic()
            if self._node_map is not None and (now - self._node_map_at) < _NODE_MAP_TTL:
                return self._node_map
            self._node_map = await self._node_map_from_solnodes()
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

    # Non-fissure worldstate: not adapted from DE here (see module docstring).
    # The fallback wrapper serves these from the primary source.
    async def fetch_void_trader(self) -> dict[str, Any]:
        return {}

    async def fetch_archon_hunt(self) -> dict[str, Any]:
        return {}

    async def fetch_alerts(self) -> list[dict[str, Any]]:
        return []

    async def fetch_invasions(self) -> list[dict[str, Any]]:
        return []

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "OfficialWorldStateSource":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
