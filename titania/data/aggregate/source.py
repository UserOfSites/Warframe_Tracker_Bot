"""Aggregate-endpoint data source.

The original Plan.md called for an `OfficialWorldStateSource` backed by
`content.warframe.com/dynamic/worldState.php`. That public endpoint has been
retired by Digital Extremes — it returns 404 as of 2026. To honour the spirit
of Phase 6 (prove the Bridge by switching sources via env), this source hits
warframestat's aggregate `/pc` endpoint, which returns the full live world
state in a single document, and extracts the `fissures` sub-field.

It demonstrates the Bridge pattern: a different orchestration path (single
aggregate fetch + field extraction) plugging into the same domain layer as
`WarframestatSource`, without changing anything above the data layer.

If DE ever republishes worldState.php, dropping a real `OfficialWorldStateSource`
in here is straightforward — only `fetch_fissures` and `fetch_node_catalog`
need to change.
"""

import logging

import httpx

from titania.data.warframestat.adapters import adapt_fissures
from titania.data.warframestat.source import _bare_node, _split_node_value
from titania.domain.fissure import Fissure
from titania.domain.node import NodeInfo

log = logging.getLogger(__name__)


class AggregateSource:
    """WarframeDataSource backed by the aggregate `/pc` endpoint."""

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
        url = f"{self._base_url}/{self._platform}"
        resp = await self._client.get(url, params={"language": "en"})
        resp.raise_for_status()
        payload = resp.json()
        return adapt_fissures(payload.get("fissures", []))

    async def fetch_void_trader(self) -> dict:
        url = f"{self._base_url}/{self._platform}"
        resp = await self._client.get(url, params={"language": "en"})
        resp.raise_for_status()
        return resp.json().get("voidTrader", {})

    async def fetch_node_catalog(self) -> frozenset[str]:
        # The aggregate endpoint doesn't ship the node catalog; reuse solnodes.
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

    async def fetch_node_details(self) -> dict[str, NodeInfo]:
        url = f"{self._base_url}/solnodes"
        resp = await self._client.get(url)
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

    async def __aenter__(self) -> "AggregateSource":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
