import logging

from titania.data.source import WarframeDataSource
from titania.domain.calendar import CalendarReward, notable_calendar_rewards

log = logging.getLogger(__name__)


class CalendarService:
    """Surfaces the current 1999-calendar season's Archon-shard / booster
    rewards for the vendors embed. Best-effort: any upstream hiccup yields an
    empty list so the embed simply omits the Calendar block rather than
    failing."""

    def __init__(self, data_source: WarframeDataSource) -> None:
        self._source = data_source

    async def notable(self) -> list[CalendarReward]:
        try:
            raw = await self._source.fetch_calendar()
        except Exception:
            log.exception("calendar fetch failed")
            return []
        return notable_calendar_rewards(raw)
