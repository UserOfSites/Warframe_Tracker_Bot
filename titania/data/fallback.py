"""Fissure fallback: prefer a primary source, drop to a secondary when the
primary has no *fresh* fissures.

warframestat.us periodically stalls — it keeps answering, but its worldstate
(fissures included) freezes hours in the past. The adapters drop already-expired
fissures, so a stalled primary yields an *empty* fissure list; that emptiness is
the signal to fall back to DE's live feed. When the primary recovers it returns
fresh fissures again and is used automatically — no manual switch-over.

Only ``fetch_fissures`` fails over (that's the observed outage and the user-
visible one). Every other worldstate method delegates straight to the primary.
"""

import logging

from titania.data.source import WarframeDataSource
from titania.domain.fissure import Fissure
from titania.domain.node import NodeInfo

log = logging.getLogger(__name__)


class FallbackDataSource:
    """Wrap ``primary``; serve fissures from ``fallback`` whenever the primary
    returns nothing fresh (stale/down). All other reads use the primary."""

    def __init__(
        self, primary: WarframeDataSource, fallback: WarframeDataSource
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        # Remember which source last served fissures so we only log on a
        # transition (avoids a warning every poll while the primary is down).
        self._on_fallback = False

    async def fetch_fissures(self) -> list[Fissure]:
        try:
            primary = await self._primary.fetch_fissures()
        except Exception:
            log.exception("primary fissure fetch failed; trying fallback")
            primary = []

        if primary:
            if self._on_fallback:
                log.info("primary fissure source recovered; switching back")
                self._on_fallback = False
            return primary

        try:
            fallback = await self._fallback.fetch_fissures()
        except Exception:
            log.exception("fallback fissure fetch failed")
            return []

        if not self._on_fallback:
            log.warning(
                "primary fissure source returned no fresh fissures; "
                "serving %d from fallback",
                len(fallback),
            )
            self._on_fallback = True
        return fallback

    async def fetch_node_catalog(self) -> frozenset[str]:
        return await self._primary.fetch_node_catalog()

    async def fetch_node_details(self) -> dict[str, NodeInfo]:
        return await self._primary.fetch_node_details()

    async def fetch_void_trader(self) -> dict:
        return await self._primary.fetch_void_trader()

    async def fetch_archon_hunt(self) -> dict:
        return await self._primary.fetch_archon_hunt()

    async def fetch_alerts(self) -> list[dict]:
        return await self._primary.fetch_alerts()

    async def fetch_invasions(self) -> list[dict]:
        return await self._primary.fetch_invasions()

    async def aclose(self) -> None:
        await self._primary.aclose()
        await self._fallback.aclose()

    async def __aenter__(self) -> "FallbackDataSource":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
