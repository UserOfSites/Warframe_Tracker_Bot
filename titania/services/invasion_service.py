import logging

from titania.data.source import WarframeDataSource
from titania.domain.invasions import NotableInvasion, notable_invasions

log = logging.getLogger(__name__)


class InvasionService:
    """Fetches active invasions and keeps only those rewarding a notable item
    (Forma, Orokin Reactor/Catalyst, Exilus Warframe Adapter). Best-effort: any
    upstream hiccup yields an empty list so the vendors embed simply omits the
    Invasions section rather than failing."""

    def __init__(self, data_source: WarframeDataSource) -> None:
        self._source = data_source

    async def notable(self) -> list[NotableInvasion]:
        try:
            raw = await self._source.fetch_invasions()
        except Exception:
            log.exception("invasions fetch failed")
            return []
        return notable_invasions(raw)
