"""Health-tracking failover across multiple upstream data sources.

Wraps an ordered list of sources (primary first) and, for every read, uses the
first healthy one that answers — so a single upstream outage no longer takes the
bot down with it. When a source raises it's marked unhealthy and skipped for a
short cooldown, then re-probed automatically; recovery needs no restart.

Two response shapes:

- **Fissures** are compared by *usable* count (non-Railjack, non-Requiem — what
  the board actually renders). warframestat has been seen answering ``200`` with
  a frozen/partial list, which a plain "first that succeeds" check would trust;
  taking the source with the most usable fissures survives that too. Ties go to
  the earlier (primary) source, so the bot returns to it once it's healthy.
- **Everything else** takes the first source that doesn't raise. An empty result
  is a valid answer (there really may be no alerts), so emptiness never triggers
  failover — only an exception does.
"""

import logging
import time
from typing import Any, Awaitable, Callable, TypeVar

from titania.data.source import WarframeDataSource
from titania.domain.era import Era
from titania.domain.fissure import Fissure
from titania.domain.node import NodeInfo
from titania.domain.railjack import is_railjack

log = logging.getLogger(__name__)

T = TypeVar("T")


def _usable(fissures: list[Fissure]) -> int:
    """Fissures the board actually renders — Railjack and Requiem are dropped
    everywhere, so they don't count toward a source's health."""
    return sum(
        1 for f in fissures if not is_railjack(f) and f.era is not Era.REQUIEM
    )


class FailoverDataSource:
    """Ordered, health-aware failover over several ``WarframeDataSource``s."""

    def __init__(
        self,
        sources: list[tuple[str, WarframeDataSource]],
        *,
        cooldown_seconds: float = 60.0,
    ) -> None:
        if not sources:
            raise ValueError("FailoverDataSource needs at least one source")
        self._sources = list(sources)
        self._cooldown = cooldown_seconds
        # source name -> monotonic time until which it's considered down.
        self._unhealthy_until: dict[str, float] = {}
        # Last source that served fissures, tracked only to log switch-overs.
        self._active: str | None = None

    def _ordered(self) -> list[tuple[str, WarframeDataSource]]:
        """Sources to try, in priority order, skipping those in cooldown. If
        every source is cooling down, try them all anyway (best effort beats
        refusing to answer)."""
        now = time.monotonic()
        healthy = [
            (n, s) for n, s in self._sources if self._unhealthy_until.get(n, 0.0) <= now
        ]
        return healthy or list(self._sources)

    def _mark_unhealthy(self, name: str, method: str, exc: Exception) -> None:
        now = time.monotonic()
        was_healthy = self._unhealthy_until.get(name, 0.0) <= now
        self._unhealthy_until[name] = now + self._cooldown
        if was_healthy:
            log.warning(
                "source %r failed on %s (%s); pausing it for %.0fs",
                name, method, type(exc).__name__, self._cooldown,
            )

    def _mark_healthy(self, name: str) -> None:
        self._unhealthy_until.pop(name, None)

    def _note_active(self, name: str) -> None:
        if self._active != name:
            if self._active is not None:
                log.info("data source switched: %s -> %s", self._active, name)
            self._active = name

    async def _first_ok(
        self, method: str, op: Callable[[WarframeDataSource], Awaitable[T]]
    ) -> T | None:
        """First source whose ``op`` doesn't raise (emptiness is a valid answer,
        so it doesn't trigger failover). ``None`` if every source raised."""
        for name, src in self._ordered():
            try:
                result = await op(src)
            except Exception as e:
                self._mark_unhealthy(name, method, e)
                continue
            self._mark_healthy(name)
            return result
        return None

    async def fetch_fissures(self) -> list[Fissure]:
        best: list[Fissure] | None = None
        best_name: str | None = None
        best_usable = -1
        for name, src in self._ordered():
            try:
                fissures = await src.fetch_fissures()
            except Exception as e:
                self._mark_unhealthy(name, "fissures", e)
                continue
            self._mark_healthy(name)
            usable = _usable(fissures)
            if usable > best_usable:  # strict: ties keep the earlier (primary)
                best, best_name, best_usable = fissures, name, usable
        if best is None:
            return []
        self._note_active(best_name)  # type: ignore[arg-type]
        return best

    async def fetch_node_catalog(self) -> frozenset[str]:
        result = await self._first_ok("node_catalog", lambda s: s.fetch_node_catalog())
        return result if result is not None else frozenset()

    async def fetch_node_details(self) -> dict[str, NodeInfo]:
        result = await self._first_ok("node_details", lambda s: s.fetch_node_details())
        return result if result is not None else {}

    async def fetch_void_trader(self) -> dict[str, Any]:
        result = await self._first_ok("void_trader", lambda s: s.fetch_void_trader())
        return result if result is not None else {}

    async def fetch_archon_hunt(self) -> dict[str, Any]:
        result = await self._first_ok("archon_hunt", lambda s: s.fetch_archon_hunt())
        return result if result is not None else {}

    async def fetch_alerts(self) -> list[dict[str, Any]]:
        result = await self._first_ok("alerts", lambda s: s.fetch_alerts())
        return result if result is not None else []

    async def fetch_invasions(self) -> list[dict[str, Any]]:
        result = await self._first_ok("invasions", lambda s: s.fetch_invasions())
        return result if result is not None else []

    async def fetch_calendar(self) -> dict[str, Any]:
        result = await self._first_ok("calendar", lambda s: s.fetch_calendar())
        return result if result is not None else {}

    async def fetch_vault_trader(self) -> dict[str, Any]:
        result = await self._first_ok("vault_trader", lambda s: s.fetch_vault_trader())
        return result if result is not None else {}

    async def aclose(self) -> None:
        for _name, src in self._sources:
            await src.aclose()

    async def __aenter__(self) -> "FailoverDataSource":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
