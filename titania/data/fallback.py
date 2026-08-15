"""Fissure fallback: pick whichever source has the more complete fissure list.

warframestat.us fails in two ways we've seen in the wild: it freezes (every
fissure hours in the past — the adapters then drop them all, leaving an empty
list) and it *degrades* (returns a partial list — e.g. 9 fissures, mostly
Railjack, when the real count is ~20). A plain "is the primary empty?" check
catches the first but not the second: a partial-but-nonzero response looks fine
yet renders a near-empty board once Railjack/Requiem are filtered out.

So instead of trusting order, we compare **usable** fissure counts — usable =
what the board actually shows (non-Railjack, non-Requiem) — and serve whichever
source has more. DE's official worldstate is authoritative and complete, so it
wins automatically whenever the primary is stalled or degraded, and the primary
is used when it's healthy (ties go to the primary to avoid needless churn).

Only fissures fail over. Every other worldstate read (vendors, alerts,
invasions, node catalog) delegates straight to the primary.
"""

import logging

from titania.data.source import WarframeDataSource
from titania.domain.era import Era
from titania.domain.fissure import Fissure
from titania.domain.node import NodeInfo
from titania.domain.railjack import is_railjack

log = logging.getLogger(__name__)


def _usable(fissures: list[Fissure]) -> int:
    """Count fissures that would actually render on the board — the same filter
    the service/refresher apply (Railjack and Requiem are dropped everywhere)."""
    return sum(
        1 for f in fissures if not is_railjack(f) and f.era is not Era.REQUIEM
    )


class FallbackDataSource:
    """Wrap ``primary``; serve fissures from whichever of ``primary`` /
    ``fallback`` has more usable fissures. All other reads use the primary."""

    def __init__(
        self, primary: WarframeDataSource, fallback: WarframeDataSource
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        # Track which source is winning so we only log on a transition (not
        # every poll while the primary is degraded).
        self._on_fallback = False

    async def _safe_fissures(self, source: WarframeDataSource, label: str) -> list[Fissure]:
        try:
            return await source.fetch_fissures()
        except Exception:
            log.exception("%s fissure fetch failed", label)
            return []

    async def fetch_fissures(self) -> list[Fissure]:
        primary = await self._safe_fissures(self._primary, "primary")
        fallback = await self._safe_fissures(self._fallback, "fallback")
        p_usable, f_usable = _usable(primary), _usable(fallback)

        # Strictly more usable fissures on the fallback => the primary is stalled
        # or degraded. Ties (incl. both zero) keep the primary.
        if f_usable > p_usable:
            if not self._on_fallback:
                log.warning(
                    "primary fissures degraded (%d usable vs %d from fallback); "
                    "serving from fallback",
                    p_usable, f_usable,
                )
                self._on_fallback = True
            return fallback

        if self._on_fallback:
            log.info(
                "primary fissure source healthy again (%d usable); switching back",
                p_usable,
            )
            self._on_fallback = False
        return primary

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
