import asyncio
import logging

import httpx

from titania.data.warframestat.adapters import adapt_fissures
from titania.domain.fissure import Fissure
from titania.domain.node import NodeInfo

log = logging.getLogger(__name__)

# Transient network errors we retry. ReadTimeout shows up on slow VPS links to
# api.warframestat.us; ConnectError / ConnectTimeout when the upstream is
# briefly unreachable. These all resolve by themselves within a few seconds.
_RETRYABLE = (
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
)


def _bare_node(value: str) -> str:
    """'Calabash (Veil)' -> 'Calabash'."""
    if "(" in value:
        return value.split("(", 1)[0].strip()
    return value.strip()


def _split_node_value(value: str) -> tuple[str, str]:
    """``'Apollodorus (Mercury)'`` → ``('Apollodorus', 'Mercury')``."""
    if "(" not in value or ")" not in value:
        return (value.strip(), "")
    bare, rest = value.split("(", 1)
    planet = rest.rsplit(")", 1)[0]
    return (bare.strip(), planet.strip())


class WarframestatSource:
    """WarframeDataSource backed by https://api.warframestat.us."""

    def __init__(
        self,
        base_url: str = "https://api.warframestat.us",
        platform: str = "pc",
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
        max_attempts: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._platform = platform
        self._owns_client = client is None
        # 30s read timeout accommodates slow VPS uplinks; the per-attempt
        # cost is capped further by the retry budget.
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._max_attempts = max_attempts

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
                    backoff = 0.5 * (2 ** attempt)  # 0.5s, 1s, 2s
                    log.warning(
                        "warframestat %s attempt %d/%d failed (%s); retrying in %.1fs",
                        url, attempt + 1, self._max_attempts, type(e).__name__, backoff,
                    )
                    await asyncio.sleep(backoff)
        assert last_exc is not None
        raise last_exc

    async def fetch_fissures(self) -> list[Fissure]:
        url = f"{self._base_url}/{self._platform}/fissures"
        resp = await self._get_with_retry(url, params={"language": "en"})
        resp.raise_for_status()
        payload = resp.json()
        return adapt_fissures(payload)

    async def fetch_void_trader(self) -> dict:
        url = f"{self._base_url}/{self._platform}/voidTrader"
        resp = await self._get_with_retry(url, params={"language": "en"})
        resp.raise_for_status()
        return resp.json()

    async def fetch_node_catalog(self) -> frozenset[str]:
        # solnodes lists every node DE has shipped — keyed `SolNode*` for
        # regular missions and `CrewBattleNode*` for Railjack. We expose only
        # regular nodes for `/settings` autocomplete since Railjack is excluded
        # globally anyway.
        url = f"{self._base_url}/solnodes"
        resp = await self._get_with_retry(url)
        resp.raise_for_status()
        payload = resp.json()
        return frozenset(
            _bare_node(entry["value"])
            for key, entry in payload.items()
            if key.startswith("SolNode")
            and isinstance(entry, dict)
            and isinstance(entry.get("value"), str)
            and "(" in entry["value"]
        )

    async def fetch_node_details(self) -> dict[str, NodeInfo]:
        """Same /solnodes endpoint as the catalog, but keeps the planet
        suffix and the per-node ``type`` (mission type) so the filter panel
        can scope node dropdowns by both planet and mission type."""
        url = f"{self._base_url}/solnodes"
        resp = await self._get_with_retry(url)
        resp.raise_for_status()
        payload = resp.json()
        out: dict[str, NodeInfo] = {}
        for key, entry in payload.items():
            if not (key.startswith("SolNode") and isinstance(entry, dict)):
                continue
            value = entry.get("value")
            if not (isinstance(value, str) and "(" in value):
                continue
            name, planet = _split_node_value(value)
            mt_raw = entry.get("type")
            if not isinstance(mt_raw, str):
                mt_raw = ""
            out[name] = NodeInfo(name=name, planet=planet, mission_type_raw=mt_raw)
        return out

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "WarframestatSource":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
