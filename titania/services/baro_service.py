import logging
from datetime import date, datetime, timezone
from typing import Any

from titania.data.baro.history import BaroHistoryClient, BaroItemHistory
from titania.data.source import WarframeDataSource
from titania.domain.baro import (
    BaroBoard,
    BaroInventoryItem,
    EnrichedBaroItem,
    VoidTraderState,
)

log = logging.getLogger(__name__)


def _parse_dt(raw: str | None) -> datetime:
    if not raw:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    cleaned = raw.replace("Z", "+00:00")
    return datetime.fromisoformat(cleaned).astimezone(timezone.utc)


def _adapt_inventory(raw: list[dict[str, Any]] | None) -> tuple[BaroInventoryItem, ...]:
    out: list[BaroInventoryItem] = []
    for entry in raw or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("item") or entry.get("name")
        if not name:
            continue
        out.append(
            BaroInventoryItem(
                name=str(name),
                ducats=_int_or_none(entry.get("ducats")),
                credits=_int_or_none(entry.get("credits")),
            )
        )
    return tuple(out)


def _int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _last_appearance_before(item: BaroItemHistory, cutoff: date) -> date | None:
    """Most recent prior appearance that's strictly earlier than ``cutoff``.
    Used so a freshly-arrived item doesn't report "0d ago" — we want the gap
    since the visit *before* this one."""
    earlier = [d for d in item.appearances if d < cutoff]
    return earlier[-1] if earlier else None


class BaroService:
    """Combines warframestat live state with wiki history.

    Caches the enriched inventory **per Baro visit** so that the wiki is
    queried only when:
      - Baro arrives (transition from absent → present), or
      - Baro's inventory rotates mid-visit (extremely rare, hasn't happened
        in years), or
      - the bot restarts while Baro is present.

    During the 2-day window Baro is here, the embed re-renders every 30s but
    none of those refreshes hit the wiki — they reuse the cached enrichment.
    """

    def __init__(
        self,
        data_source: WarframeDataSource,
        history: BaroHistoryClient,
    ) -> None:
        self._source = data_source
        self._history = history
        # Visit-scoped cache. Key: (activation_iso, frozenset(item_names)).
        self._cached_visit_key: tuple[str, frozenset[str]] | None = None
        self._cached_enriched: tuple[EnrichedBaroItem, ...] = ()

    async def fetch_state(self) -> VoidTraderState:
        raw = await self._source.fetch_void_trader()
        return VoidTraderState(
            character=str(raw.get("character") or "Baro Ki'Teer"),
            location=str(raw.get("location") or ""),
            activation=_parse_dt(raw.get("activation")),
            expiry=_parse_dt(raw.get("expiry")),
            inventory=_adapt_inventory(raw.get("inventory")),
        )

    async def board(self) -> BaroBoard:
        state = await self.fetch_state()
        now = datetime.now(timezone.utc)
        if not state.is_present:
            # Baro left — drop the cache so the next visit starts clean.
            self._cached_visit_key = None
            self._cached_enriched = ()
            return BaroBoard(state=state, enriched_inventory=(), generated_at=now)

        # Reuse the enriched inventory if this is the same visit we already
        # looked up. The visit key includes the inventory item names so a
        # mid-visit rotation (very rare) invalidates the cache automatically.
        visit_key = (
            state.activation.isoformat(),
            frozenset(item.name for item in state.inventory),
        )
        if self._cached_visit_key == visit_key:
            return BaroBoard(
                state=state,
                enriched_inventory=self._cached_enriched,
                generated_at=now,
            )

        history_index = await self._history.lookup(item.name for item in state.inventory)
        current_visit_date = state.activation.date()
        enriched: list[EnrichedBaroItem] = []
        for item in state.inventory:
            history = history_index.get(item.name)
            if history is None:
                enriched.append(
                    EnrichedBaroItem(
                        name=item.name,
                        ducats=item.ducats,
                        credits=item.credits,
                        last_appearance=None,
                        total_appearances=0,
                        image_name=None,
                    )
                )
                continue
            enriched.append(
                EnrichedBaroItem(
                    name=item.name,
                    ducats=item.ducats,
                    credits=item.credits,
                    last_appearance=_last_appearance_before(history, current_visit_date),
                    total_appearances=len(history.appearances),
                    image_name=history.image,
                )
            )
        enriched_tuple = tuple(enriched)
        self._cached_visit_key = visit_key
        self._cached_enriched = enriched_tuple
        return BaroBoard(
            state=state,
            enriched_inventory=enriched_tuple,
            generated_at=now,
        )
