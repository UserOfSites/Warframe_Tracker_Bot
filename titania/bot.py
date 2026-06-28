import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from titania.data.baro.history import BaroHistoryClient
from titania.services.baro_service import BaroService
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
        log.info("synced %d application commands", len(synced))
        await self.emoji_registry.sync(self)
        # The registry is populated now, so the reaction subscriber can build
        # its emoji-id → topic lookup table for incoming reaction events.
        self.reaction_subscriber.reload_emoji_map()
        self.refresher.start()

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self.reaction_subscriber.handle_add(payload)

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        await self.reaction_subscriber.handle_remove(payload)

    async def on_ready(self) -> None:
        log.info("logged in as %s (id=%s)", self.user, self.user.id if self.user else "?")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="Void Fissures"
            )
        )

    async def close(self) -> None:
        await self.refresher.stop()
        await self.baro_history.aclose()
        await super().close()
