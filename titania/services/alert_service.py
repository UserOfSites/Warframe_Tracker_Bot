import logging

from titania.data.source import WarframeDataSource
from titania.domain.alerts import AlertEntry, active_alerts

log = logging.getLogger(__name__)


class AlertService:
    """Fetches all currently-active alerts for the vendors embed. Best-effort:
    any upstream hiccup yields an empty list so the embed simply omits the
    Alerts section rather than failing."""

    def __init__(self, data_source: WarframeDataSource) -> None:
        self._source = data_source

    async def active(self) -> list[AlertEntry]:
        try:
            raw = await self._source.fetch_alerts()
        except Exception:
            log.exception("alerts fetch failed")
            return []
        return active_alerts(raw)
