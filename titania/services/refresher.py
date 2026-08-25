import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord

from titania.domain.era import Era
from titania.domain.railjack import is_railjack
from titania.i18n.translator import Translator
from titania.presentation.embeds import build_fissure_embed
from titania.presentation.vendor_embed import (
    build_baro_inventory_embed,
    build_vendors_embed,
)
from titania.storage.tracked_channels_repo import TrackedChannel

if TYPE_CHECKING:
    from titania.bot import TitaniaBot

log = logging.getLogger(__name__)


class FissureRefresher:
    """Background loop: warms the data-source cache and re-renders every
    tracked channel's embed on a fixed interval. Resilient — one bad channel
    (deleted message, permission revoked, etc.) doesn't break the others, and
    a missing message is auto-untracked."""

    # When a fissure expires the cache refetches, so we want to tick right then
    # rather than up to a full interval later. The buffer gives upstream a beat
    # to publish the replacement rotation before we refetch; the floor stops a
    # just-expired fissure (or clock skew) from busy-looping.
    _EXPIRY_BUFFER_SECONDS = 1.5
    _MIN_WAKE_SECONDS = 2.0

    def __init__(self, bot: "TitaniaBot", interval_seconds: float = 30.0) -> None:
        self._bot = bot
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="fissure-refresher")
        log.info("refresher started (interval=%.1fs)", self._interval)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            wake = self._interval
            try:
                wake = await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("refresher tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=wake)
            except TimeoutError:
                pass

    async def tick(self) -> float:
        """Refresh every tracked channel and return how many seconds to sleep
        before the next tick — the soonest fissure expiry (so a rotation shows
        almost immediately), clamped to ``[_MIN_WAKE, interval]``."""
        # Warm caches once per tick so the tracked-channel renders are fast, and
        # reuse the warmed list to time the next wake-up.
        all_fissures = await self._bot.data_source.fetch_fissures()
        await self._refresh_kind(
            await self._bot.tracked_repo.list_all(),
            self._bot.tracked_repo,
            self.build_fissures_embed,
            label="fissures",
        )
        await self._refresh_kind(
            await self._bot.tracked_vendors_repo.list_all(),
            self._bot.tracked_vendors_repo,
            self.build_vendors_embed,
            label="vendors",
        )
        try:
            await self._dispatch_notifications()
        except Exception:
            log.exception("notification dispatch failed")
        return self._next_wake_seconds(all_fissures)

    def _next_wake_seconds(self, fissures) -> float:
        """Sleep until just after the soonest fissure expires (when the cache
        next refetches), capped by the baseline interval so vendors/alerts still
        refresh regularly and floored so we never busy-loop."""
        now = datetime.now(timezone.utc)
        future = [f.expires_at for f in fissures if f.expires_at > now]
        if not future:
            return self._interval
        secs = (min(future) - now).total_seconds() + self._EXPIRY_BUFFER_SECONDS
        return max(self._MIN_WAKE_SECONDS, min(self._interval, secs))

    async def _dispatch_notifications(self) -> None:
        """Edge-trigger DMs to subscribers when matching fissures go live.

        Subscriptions are global per user, so this is one pass — no per-guild
        loop, no chance of duplicate DMs from multi-server users. Runs after
        the embed refresh so a failure here doesn't block the visible tracker.
        """
        if not await self._bot.subscriptions_repo.any_subscribers():
            return
        all_fissures = [
            f
            for f in await self._bot.data_source.fetch_fissures()
            if not is_railjack(f) and f.era is not Era.REQUIEM
        ]
        await self._bot.notifier.process(all_fissures)

    async def _refresh_kind(
        self,
        tracked: list[TrackedChannel],
        repo,
        build_embed,
        label: str,
    ) -> None:
        for tc in tracked:
            try:
                embed = await build_embed(tc.guild_id)
                await self._edit_message(tc, embed)
            except discord.NotFound:
                log.info(
                    "%s tracked message gone for guild %s; untracking",
                    label,
                    tc.guild_id,
                )
                await repo.delete(tc.guild_id)
            except discord.Forbidden:
                log.warning(
                    "missing permissions for %s tracking guild=%s channel=%s; untracking",
                    label,
                    tc.guild_id,
                    tc.channel_id,
                )
                await repo.delete(tc.guild_id)
            except Exception:
                log.exception(
                    "%s refresh failed for guild=%s channel=%s",
                    label,
                    tc.guild_id,
                    tc.channel_id,
                )

    async def _edit_message(
        self, tc: TrackedChannel, embed: discord.Embed
    ) -> None:
        channel = self._bot.get_channel(tc.channel_id)
        if channel is None:
            channel = await self._bot.fetch_channel(tc.channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            raise RuntimeError(f"channel {tc.channel_id} is not messageable")
        message = await channel.fetch_message(tc.message_id)
        await message.edit(embed=embed)

    async def build_fissures_embed(self, guild_id: int | None) -> discord.Embed:
        settings = await self._bot.settings_repo.get(guild_id)
        translator = Translator(settings.locale)
        board = await self._bot.fissure_service.board_for_guild(guild_id)
        return build_fissure_embed(
            board,
            translator,
            self._bot.emoji_registry,
            excellent_nodes=settings.excellent_nodes,
            good_nodes=settings.good_nodes,
        )

    async def build_vendors_embed(self, guild_id: int | None) -> discord.Embed:
        """Multi-vendor **summary** embed (tracked channels + ``/vendors baro``).
        Cheap: no per-item emoji uploads — the full item grid is built lazily
        by :meth:`build_baro_inventory_embed` only when a user asks for it."""
        settings = await self._bot.settings_repo.get(guild_id)
        translator = Translator(settings.locale)
        board = await self._bot.baro_service.board()
        archon = await self._bot.archon_service.current()
        alerts = await self._bot.alert_service.active()
        invasions = await self._bot.invasion_service.notable()
        calendar = await self._bot.calendar_service.notable()
        varzia = await self._bot.varzia_service.rotation()
        # Upload each notable invasion's reward icon on demand (they're rare, so
        # this stays off the hot path in practice) and map image_name → markup.
        invasion_icons: dict[str, str] = {}
        for inv in invasions:
            if not inv.image_name:
                continue
            markup = await self._bot.item_emoji_cache.ensure(self._bot, inv.image_name)
            if markup:
                invasion_icons[inv.image_name] = markup
        return build_vendors_embed(
            board,
            translator,
            self._bot.emoji_registry,
            archon=archon,
            alerts=alerts,
            invasions=invasions,
            invasion_icons=invasion_icons,
            calendar=calendar,
            varzia=varzia,
            inventory_mention=self._bot.command_mention("vendors inventory"),
        )

    async def build_baro_inventory_embed(self, guild_id: int | None) -> discord.Embed:
        """Baro's full inventory embed — served ephemerally by
        ``/vendors inventory``. Uploads item icons on demand (only when Baro is
        actually present), which is why it's kept off the 30s refresh path."""
        settings = await self._bot.settings_repo.get(guild_id)
        translator = Translator(settings.locale)
        board = await self._bot.baro_service.board()
        item_icons: dict[str, str] = {}
        if board.state.is_present:
            for entry in board.enriched_inventory:
                if not entry.image_name:
                    continue
                markup = await self._bot.item_emoji_cache.ensure(
                    self._bot, entry.image_name
                )
                if markup:
                    item_icons[entry.image_name] = markup
        return build_baro_inventory_embed(
            board, translator, self._bot.emoji_registry, item_icons
        )

    # Backwards-compat alias for the existing /fissures cog and tests.
    async def build_embed(self, guild_id: int | None) -> discord.Embed:
        return await self.build_fissures_embed(guild_id)
