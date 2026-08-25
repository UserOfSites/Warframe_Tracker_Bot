import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from titania.data.baro.history import BaroHistoryClient
from titania.services.alert_service import AlertService
from titania.services.archon_service import ArchonService
from titania.services.baro_service import BaroService
from titania.services.calendar_service import CalendarService
from titania.services.varzia_service import VarziaService
from titania.services.invasion_service import InvasionService
from titania.services.emoji_registry import EmojiRegistry, ItemEmojiCache
from titania.services.fissure_service import FissureService
from titania.services.notifier import FissureNotifier
from titania.services.reaction_subscriber import ReactionSubscriber
from titania.services.refresher import FissureRefresher
from titania.storage.fissure_subscriptions_repo import FissureSubscriptionsRepository
from titania.storage.guild_settings_repo import GuildSettingsRepository
from titania.storage.tracked_channels_repo import TrackedChannelsRepository
from titania.storage.tracked_vendors_repo import TrackedVendorsRepository
from titania.storage.user_notification_messages_repo import (
    UserNotificationMessagesRepository,
)
from titania.storage.user_preferences_repo import UserPreferencesRepository

if TYPE_CHECKING:
    from titania.config import Config
    from titania.data.source import WarframeDataSource
    from titania.storage.db import Database

log = logging.getLogger(__name__)

INITIAL_COGS = (
    "titania.cogs.ping",
    "titania.cogs.fissures",
    "titania.cogs.settings",
    "titania.cogs.tracking",
    "titania.cogs.vendors",
    "titania.cogs.notifications",
    "titania.cogs.language",
    "titania.cogs.help",
)


class TitaniaBot(commands.Bot):
    def __init__(
        self,
        config: "Config",
        data_source: "WarframeDataSource",
        db: "Database",
    ) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.config = config
        self.data_source = data_source
        self.db = db
        self.settings_repo = GuildSettingsRepository(db, config)
        self.tracked_repo = TrackedChannelsRepository(db)
        self.tracked_vendors_repo = TrackedVendorsRepository(db)
        self.subscriptions_repo = FissureSubscriptionsRepository(db)
        self.user_preferences_repo = UserPreferencesRepository(db)
        self.user_notification_messages_repo = UserNotificationMessagesRepository(db)
        self.fissure_service = FissureService(
            data_source=data_source,
            settings_resolver=self.settings_repo.get,
        )
        self.baro_history = BaroHistoryClient()
        self.baro_service = BaroService(data_source, self.baro_history)
        self.archon_service = ArchonService(data_source)
        self.alert_service = AlertService(data_source)
        self.invasion_service = InvasionService(data_source)
        self.calendar_service = CalendarService(data_source)
        self.varzia_service = VarziaService(data_source)
        # Filled after the command tree syncs; used to render clickable
        # slash-command mentions (``</vendors inventory:ID>``) inside embeds.
        self._app_command_ids: dict[str, int] = {}
        # Roots we've already warned about, so command_mention logs at most once
        # per unresolved command instead of every render.
        self._warned_missing_mentions: set[str] = set()
        self.emoji_registry = EmojiRegistry()
        self.item_emoji_cache = ItemEmojiCache()
        self.notifier = FissureNotifier(self)
        self.reaction_subscriber = ReactionSubscriber(self)
        self.refresher = FissureRefresher(self, interval_seconds=config.fissure_cache_ttl)

    async def setup_hook(self) -> None:
        for cog in INITIAL_COGS:
            await self.load_extension(cog)
            log.info("loaded cog %s", cog)
        synced = await self.tree.sync()
        self._app_command_ids = {c.name: c.id for c in synced}
        log.info("synced %d application commands", len(synced))
        # A rate-limited/partial sync can come back without our command ids,
        # which would silently break slash-command mentions (e.g. the Baro
        # inventory link). Recover them directly from Discord in that case.
        if not self._app_command_ids:
            await self._refresh_command_ids()
        await self.emoji_registry.sync(self)
        # The registry is populated now, so the reaction subscriber can build
        # its emoji-id → topic lookup table for incoming reaction events.
        self.reaction_subscriber.reload_emoji_map()
        # Backfill reactions for any topic added since a tracker was posted
        # (e.g. Defences) so existing tracked messages gain the new reaction
        # without being deleted and re-posted.
        try:
            await self.reaction_subscriber.reseed_tracked_messages()
        except Exception:
            log.exception("failed to reseed reactions on tracked messages")
        self.refresher.start()

    async def _refresh_command_ids(self) -> None:
        """Repopulate ``_app_command_ids`` from Discord's registered commands.
        Authoritative and independent of the ``tree.sync`` return value, so it
        recovers ids after a sync that came back empty/partial."""
        try:
            cmds = await self.tree.fetch_commands()
        except discord.HTTPException:
            log.exception("failed to fetch application command ids")
            return
        if cmds:
            self._app_command_ids = {c.name: c.id for c in cmds}
            log.info("refreshed %d application command ids", len(self._app_command_ids))

    def command_mention(self, qualified_name: str) -> str | None:
        """``"vendors inventory"`` → ``"</vendors inventory:1234>"``, a native
        clickable slash-command link. Subcommands mention against their root
        group's id. Returns ``None`` before the tree has synced (or if the
        root command is unknown) so callers can fall back to plain text.
        """
        root = qualified_name.split(" ", 1)[0]
        cmd_id = self._app_command_ids.get(root)
        if cmd_id is None:
            # Missing id => the mention silently degrades to plain text. Log it
            # (once per unknown root) so the cause is diagnosable next time.
            if root not in self._warned_missing_mentions:
                self._warned_missing_mentions.add(root)
                log.warning(
                    "no synced command id for %r; slash-command mentions will "
                    "fall back to plain text until command ids refresh", root,
                )
            return None
        return f"</{qualified_name}:{cmd_id}>"

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self.reaction_subscriber.handle_add(payload)

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        await self.reaction_subscriber.handle_remove(payload)

    async def on_raw_reaction_clear(self, payload: discord.RawReactionClearEvent) -> None:
        # A bulk "clear reactions" wipes our seed icons but doesn't unsubscribe
        # anyone (that's per-user removes only) — re-seed so the buttons return.
        await self.reaction_subscriber.handle_clear(payload)

    async def on_raw_reaction_clear_emoji(
        self, payload: discord.RawReactionClearEmojiEvent
    ) -> None:
        await self.reaction_subscriber.handle_clear(payload)

    async def on_ready(self) -> None:
        log.info("logged in as %s (id=%s)", self.user, self.user.id if self.user else "?")
        # Safety net: if the startup sync never populated the command ids (so
        # slash-command mentions like the Baro inventory link are broken), try
        # again now — this also runs on reconnects, so it self-heals.
        if not self._app_command_ids:
            await self._refresh_command_ids()
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="Void Fissures"
            )
        )

    async def close(self) -> None:
        await self.refresher.stop()
        await self.baro_history.aclose()
        await super().close()
