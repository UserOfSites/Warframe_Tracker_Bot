import logging

from titania.data.source import WarframeDataSource
from titania.domain.varzia import VarziaRotation, varzia_rotation

log = logging.getLogger(__name__)


class VarziaService:
    """Surfaces Varzia's current (and next-if-announced) Prime Resurgence
    rotation for the vendors embed. Best-effort: any upstream hiccup yields
    ``None`` so the embed omits the Varzia block rather than failing."""

    def __init__(self, data_source: WarframeDataSource) -> None:
        self._source = data_source

    async def rotation(self) -> VarziaRotation | None:
        try:
            raw = await self._source.fetch_vault_trader()
        except Exception:
            log.exception("vault trader fetch failed")
            return None
        return varzia_rotation(raw)
