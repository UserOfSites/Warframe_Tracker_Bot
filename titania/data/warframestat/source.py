import logging

import httpx

from titania.data.warframestat.adapters import adapt_fissures
from titania.domain.fissure import Fissure

log = logging.getLogger(__name__)


def _bare_node(value: str) -> str:
    """'Calabash (Veil)' -> 'Calabash'."""
    if "(" in value:
        return value.split("(", 1)[0].strip()
    return value.strip()


class WarframestatSource:
    """WarframeDataSource backed by https://api.warframestat.us."""

    def __init__(
        self,
        base_url: str = "https://api.warframestat.us",
        platform: str = "pc",
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._platform = platform
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def fetch_fissures(self) -> list[Fissure]:
        url = f"{self._base_url}/{self._platform}/fissures"
        resp = await self._client.get(url, params={"language": "en"})
        resp.raise_for_status()
        payload = resp.json()
        return adapt_fissures(payload)

    async def fetch_void_trader(self) -> dict:
        url = f"{self._base_url}/{self._platform}/voidTrader"
        resp = await self._client.get(url, params={"language": "en"})
        resp.raise_for_status()
        return resp.json()

    async def fetch_node_catalog(self) -> frozenset[str]:
        # solnodes lists every node DE has shipped — keyed `SolNode*` for
        # regular missions and `CrewBattleNode*` for Railjack. We expose only
        # regular nodes for `/settings` autocomplete since Railjack is excluded
        # globally anyway.
        url = f"{self._base_url}/solnodes"
        resp = await self._client.get(url)
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

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "WarframestatSource":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
