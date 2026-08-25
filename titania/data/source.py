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

    async def fetch_archon_hunt(self) -> dict[str, Any]:
        """Raw Archon-Hunt payload. The only field we read is ``boss`` (the
        current Archon's name); the ArchonService maps it to a shard colour."""
        ...

    async def fetch_alerts(self) -> list[dict[str, Any]]:
        """Raw alerts payload (list). Each entry has ``mission`` (with its
        ``reward``) and ``expiry``; the alerts domain filters to notable-only."""
        ...

    async def fetch_invasions(self) -> list[dict[str, Any]]:
        """Raw invasions payload (list). Each entry has ``attacker``/``defender``
        (each with a ``reward`` incl. a ``thumbnail`` icon URL); the invasions
        domain filters to notable-reward-only."""
        ...

    async def fetch_calendar(self) -> dict[str, Any]:
        """Raw 1999-calendar payload (warframestat's parsed ``/calendar``). Keys:
        ``activation``, ``expiry``, ``days`` (each with ``date`` and ``events``,
        every event carrying a friendly ``reward`` name); the calendar domain
        filters to notable Archon-shard / booster rewards."""
        ...

    async def fetch_vault_trader(self) -> dict[str, Any]:
        """Raw Varzia / Prime-Resurgence payload (warframestat's parsed
        ``/vaultTrader``). Keys: ``location``, ``activation``, ``expiry``,
        ``inventory`` and ``schedule`` (``{expiry, item}`` per rotation, future
        ones included once announced); the varzia domain derives the current and
        next featured rotation."""
        ...

    async def aclose(self) -> None: ...

    async def __aenter__(self) -> "WarframeDataSource":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
