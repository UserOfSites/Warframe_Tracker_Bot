import logging

from titania.data.source import WarframeDataSource
from titania.domain.vendors import ArchonShard, resolve_archon

log = logging.getLogger(__name__)


class ArchonService:
    """Resolves the current Archon Hunt boss to the Archon Shard it awards.

    Deliberately best-effort: any upstream hiccup returns ``None`` so the
    vendors embed simply drops the Archon line rather than failing the whole
    render. The underlying fetch is served from ``CachedDataSource`` (cached
    until the weekly Archon rotation), so calling this every refresh tick is
    cheap.
    """

    def __init__(self, data_source: WarframeDataSource) -> None:
        self._source = data_source

    async def current(self) -> ArchonShard | None:
        try:
            raw = await self._source.fetch_archon_hunt()
        except Exception:
            log.exception("archon hunt fetch failed")
            return None
        boss = raw.get("boss") if isinstance(raw, dict) else None
        return resolve_archon(boss)
