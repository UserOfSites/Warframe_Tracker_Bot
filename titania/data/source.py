from typing import Any, Protocol, runtime_checkable

from titania.domain.fissure import Fissure
from titania.domain.node import NodeInfo


@runtime_checkable
class WarframeDataSource(Protocol):
    """Bridge abstraction: anywhere the bot reads upstream Warframe data.

    Sources return the **unfiltered** list. Filtering (mission-type, blocked
    nodes, dojoshare promotion) is a service-layer concern so the cache stays
    shared across guilds with different filter settings.
    """

    async def fetch_fissures(self) -> list[Fissure]: ...

    async def fetch_node_catalog(self) -> frozenset[str]:
        """Bare node names (no planet suffix) of every regular mission node.
        Used for autocomplete and validation in `/settings` commands."""
        ...

    async def fetch_node_details(self) -> dict[str, NodeInfo]:
        """``{bare_node_name: NodeInfo(name, planet, mission_type_raw)}`` for
        every regular mission node. Used by the filter panel to populate
        per-(planet, mission_type) node multi-selects."""
        ...

    async def fetch_void_trader(self) -> dict[str, Any]:
        """Raw void-trader payload — the BaroService normalizes it. Keys:
        ``character``, ``location``, ``activation``, ``expiry``, ``inventory``
        (list, empty when Baro isn't here)."""
        ...

    async def aclose(self) -> None: ...

    async def __aenter__(self) -> "WarframeDataSource":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
