import logging

from titania.data.source import WarframeDataSource
from titania.domain.alerts import NotableAlert, notable_alerts

log = logging.getLogger(__name__)


class AlertService:
    """Fetches active alerts and keeps only the notable ones (potatoes, Forma,
    Exilus adapters). Best-effort: any upstream hiccup yields an empty list so
    the vendors embed simply omits the Alerts section rather than failing."""

    def __init__(self, data_source: WarframeDataSource) -> None:
        self._source = data_source

    async def notable(self) -> list[NotableAlert]:
        try:
            raw = await self._source.fetch_alerts()
        except Exception:
            log.exception("alerts fetch failed")
            return []
        return notable_alerts(raw)
