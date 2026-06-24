"""Wiki-sourced Baro Ki'Teer offering history.

The Warframe wiki maintains ``Module:Baro/data`` — a Lua table containing every
item Baro has ever offered, with all historical appearance dates (cross-
platform, PC-legacy, and console-legacy). It's the canonical community record;
each visit, wiki editors append the latest date to the relevant items.

This module fetches the Lua source, parses it via ``slpp``, and exposes a
small in-memory store keyed by canonical item name. The bot uses it to answer
"when was this item last available?" for every item in the live inventory.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable

import httpx
from slpp import slpp as lua  # type: ignore[import-untyped]

log = logging.getLogger(__name__)

_WIKI_API = "https://wiki.warframe.com/api.php"
_MODULE_PAGE = "Module:Baro/data"
# In-process TTL. The hot path is the BaroService per-visit cache, which keeps
# the wiki out of the loop entirely during Baro's stay. This TTL only matters
# if a `lookup()` call escapes that cache (Baro just arrived or container
# just restarted) — we don't want a tight retry loop spamming the wiki if
# someone runs /vendors baro repeatedly in those moments.
_DEFAULT_TTL = 3600


@dataclass(frozen=True)
class BaroItemHistory:
    name: str
    ducat_cost: int | None
    credit_cost: int | None
    image: str | None
    item_type: str | None
    appearances: tuple[date, ...]  # sorted ascending

    @property
    def last_appearance(self) -> date | None:
        return self.appearances[-1] if self.appearances else None


def _parse_date(raw: str) -> date | None:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _all_dates(entry: dict) -> list[date]:
    seen: set[date] = set()
    for key in ("OfferingDates", "PcOfferingDates", "ConsoleOfferingDates"):
        for raw in entry.get(key, []) or []:
            d = _parse_date(raw)
            if d is not None:
                seen.add(d)
    return sorted(seen)


class BaroHistoryClient:
    """Fetches the wiki's ``Module:Baro/data`` Lua table on demand.

    Used only when ``BaroService`` needs to look up the last-seen dates for
    the items in Baro's *current* inventory. That happens at most once per
    Baro visit (or once per container restart during a visit). The in-memory
    cache here is a guard against tight retry loops; the real "don't query
    the wiki" optimization lives in the per-visit cache in BaroService.
    """

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        ttl_seconds: float = _DEFAULT_TTL,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._ttl = ttl_seconds
        self._items: dict[str, BaroItemHistory] = {}
        self._loaded_at: float = 0.0  # monotonic time of last in-process load
        self._lock = asyncio.Lock()

    async def items(self) -> dict[str, BaroItemHistory]:
        """Lazily-fetched name → history map. Refreshes on TTL miss."""
        now = time.monotonic()
        if self._items and (now - self._loaded_at) < self._ttl:
            return self._items
        async with self._lock:
            now = time.monotonic()
            if self._items and (now - self._loaded_at) < self._ttl:
                return self._items
            try:
                fresh = await self._fetch_and_parse()
            except Exception:
                if self._items:
                    log.exception("baro history refresh failed; using stale cache")
                    return self._items
                raise
            self._items = fresh
            self._loaded_at = time.monotonic()
            log.info("baro history refreshed from wiki: %d items", len(fresh))
            return self._items

    async def lookup(self, names: Iterable[str]) -> dict[str, BaroItemHistory]:
        """Resolve multiple item names in one go, case- and whitespace-tolerant."""
        catalog = await self.items()
        # Build a normalized index once per call (the catalog is small enough).
        index: dict[str, BaroItemHistory] = {
            _norm(item.name): item for item in catalog.values()
        }
        out: dict[str, BaroItemHistory] = {}
        for n in names:
            hit = index.get(_norm(n))
            if hit is not None:
                out[n] = hit
        return out

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _fetch_and_parse(self) -> dict[str, BaroItemHistory]:
        params = {
            "action": "parse",
            "page": _MODULE_PAGE,
            "format": "json",
            "prop": "wikitext",
        }
        resp = await self._client.get(_WIKI_API, params=params, follow_redirects=True)
        resp.raise_for_status()
        payload = resp.json()
        try:
            text = payload["parse"]["wikitext"]["*"]
        except KeyError as e:
            raise RuntimeError(f"unexpected wiki response shape: {payload!r}") from e
        return _parse_lua(text)


def _parse_lua(source: str) -> dict[str, BaroItemHistory]:
    start = source.find("return ")
    if start < 0:
        raise RuntimeError("baro lua module missing 'return' clause")
    table_src = source[start + len("return ") :].strip()
    parsed = lua.decode(table_src)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"baro lua module didn't decode to a table: {type(parsed)}")
    raw_items = parsed.get("Items") or {}
    out: dict[str, BaroItemHistory] = {}
    for key, entry in raw_items.items():
        if not isinstance(entry, dict):
            continue
        name = entry.get("Name") or key
        out[name] = BaroItemHistory(
            name=name,
            ducat_cost=entry.get("DucatCost"),
            credit_cost=entry.get("CreditCost"),
            image=entry.get("Image"),
            item_type=entry.get("Type"),
            appearances=tuple(_all_dates(entry)),
        )
    return out


def _norm(s: str) -> str:
    return " ".join(s.strip().lower().split())


def humanize_since(d: date | None, now: datetime | None = None) -> str:
    """Compact "Xd Yh Zm ago" / "X y Yd ago" formatter. None → 'never'."""
    if d is None:
        return "never"
    now = now or datetime.now(timezone.utc)
    delta = now - datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    total_minutes = max(int(delta.total_seconds() // 60), 0)
    days, rem = divmod(total_minutes, 60 * 24)
    hours, minutes = divmod(rem, 60)
    if days >= 365:
        years, day_rem = divmod(days, 365)
        return f"{years}y {day_rem}d ago"
    if days > 0:
        return f"{days}d {hours}h ago"
    if hours > 0:
        return f"{hours}h {minutes}m ago"
    return f"{minutes}m ago"
