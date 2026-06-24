import asyncio
import logging
from typing import TYPE_CHECKING

import discord

from titania.i18n.translator import Translator
from titania.presentation.embeds import build_fissure_embed
from titania.presentation.vendor_embed import build_vendors_embed
from titania.storage.tracked_channels_repo import TrackedChannel

if TYPE_CHECKING:
    from titania.bot import TitaniaBot

log = logging.getLogger(__name__)


class FissureRefresher:
    """Background loop: warms the data-source cache and re-renders every
    tracked channel's embed on a fixed interval. Resilient — one bad channel
    (deleted message, permission revoked, etc.) doesn't break the others, and
    a missing message is auto-untracked."""

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
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("refresher tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except TimeoutError:
                pass

    async def tick(self) -> None:
        # Warm caches once per tick so the tracked-channel renders are fast.
        await self._bot.data_source.fetch_fissures()
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
        return build_fissure_embed(board, translator, self._bot.emoji_registry)

    async def build_vendors_embed(self, guild_id: int | None) -> discord.Embed:
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
        return build_vendors_embed(
            board, translator, self._bot.emoji_registry, item_icons
        )

    # Backwards-compat alias for the existing /fissures cog and tests.
    async def build_embed(self, guild_id: int | None) -> discord.Embed:
        return await self.build_fissures_embed(guild_id)
