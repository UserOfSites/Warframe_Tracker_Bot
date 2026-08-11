from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from titania.data.fake.source import InMemoryFakeSource
from titania.domain.mission_type import FAST_MISSIONS
from titania.services.emoji_registry import EmojiRegistry
from titania.services.fissure_service import FissureService
from titania.services.guild_settings import GuildSettings, static_resolver
from titania.services.refresher import FissureRefresher
from titania.storage.tracked_channels_repo import TrackedChannel


@dataclass
class _FakeTrackedRepo:
    rows: list[TrackedChannel] = field(default_factory=list)
    deleted: list[int] = field(default_factory=list)

    async def list_all(self):
        return list(self.rows)

    async def delete(self, guild_id: int):
        self.deleted.append(guild_id)
        self.rows = [r for r in self.rows if r.guild_id != guild_id]


@dataclass
class _NoopVendorsRepo:
    """Vendor tracking off in these tests — the refresher loop skips them."""

    async def list_all(self):
        return []

    async def delete(self, _guild_id: int):
        return None


class _FakeBot:
    def __init__(self):
        self.data_source = InMemoryFakeSource.from_fixtures()
        self.settings_repo = MagicMock()
        default_settings = GuildSettings(
            allowed_mission_types=FAST_MISSIONS,
            blocked_nodes=frozenset(),
            pinned_nodes=frozenset(),
            dojoshare_nodes=frozenset(),
            locale="en",
        )
        self.settings_repo.get = AsyncMock(return_value=default_settings)
        self.fissure_service = FissureService(
            self.data_source, static_resolver(default_settings)
        )
        self.tracked_repo = _FakeTrackedRepo()
        self.tracked_vendors_repo = _NoopVendorsRepo()
        self.baro_service = MagicMock()
        self.baro_service.board = AsyncMock(side_effect=AssertionError("vendors disabled in this fake bot"))
        self.emoji_registry = EmojiRegistry()  # empty cache; renderers fall back to text
        # Discord client API used by refresher
        self.get_channel = MagicMock(return_value=None)
        self.fetch_channel = AsyncMock()


@pytest.fixture
def bot():
    return _FakeBot()


async def test_build_embed_uses_guild_locale(bot):
    refresher = FissureRefresher(bot)
    embed = await refresher.build_embed(123)
    assert embed.title == "Active Void Fissures"


async def test_build_embed_italian_when_guild_uses_italian(bot):
    bot.settings_repo.get = AsyncMock(
        return_value=GuildSettings(
            allowed_mission_types=FAST_MISSIONS,
            blocked_nodes=frozenset(),
            pinned_nodes=frozenset(),
            dojoshare_nodes=frozenset(),
            locale="it",
        )
    )
    refresher = FissureRefresher(bot)
    embed = await refresher.build_embed(123)
    assert embed.title == "Fissure del Vuoto attive"


async def test_tick_with_no_tracked_channels_still_warms_cache(bot):
    refresher = FissureRefresher(bot)
    # No tracked channels — tick should complete cleanly.
    await refresher.tick()
    assert bot.tracked_repo.deleted == []


async def test_tick_auto_untracks_when_message_missing(bot):
    bot.tracked_repo.rows = [TrackedChannel(guild_id=1, channel_id=100, message_id=200)]
    # Channel fetch yields a channel whose fetch_message raises NotFound.
    fake_channel = MagicMock(spec=discord.TextChannel)
    fake_channel.fetch_message = AsyncMock(
        side_effect=discord.NotFound(MagicMock(status=404), "message gone")
    )
    bot.get_channel = MagicMock(return_value=fake_channel)

    refresher = FissureRefresher(bot)
    await refresher.tick()

    assert bot.tracked_repo.deleted == [1]


async def test_tick_auto_untracks_on_permission_loss(bot):
    bot.tracked_repo.rows = [TrackedChannel(guild_id=2, channel_id=100, message_id=200)]
    fake_channel = MagicMock(spec=discord.TextChannel)
    fake_channel.fetch_message = AsyncMock(
        side_effect=discord.Forbidden(MagicMock(status=403), "no perm")
    )
    bot.get_channel = MagicMock(return_value=fake_channel)

    refresher = FissureRefresher(bot)
    await refresher.tick()

    assert bot.tracked_repo.deleted == [2]


async def test_tick_isolates_failures_between_channels(bot):
    bot.tracked_repo.rows = [
        TrackedChannel(guild_id=1, channel_id=100, message_id=200),
        TrackedChannel(guild_id=2, channel_id=300, message_id=400),
    ]

    good_msg = MagicMock()
    good_msg.edit = AsyncMock()
    good_channel = MagicMock(spec=discord.TextChannel)
    good_channel.fetch_message = AsyncMock(return_value=good_msg)

    bad_channel = MagicMock(spec=discord.TextChannel)
    bad_channel.fetch_message = AsyncMock(
        side_effect=discord.NotFound(MagicMock(status=404), "gone")
    )

    def get_channel_side_effect(cid: int):
        return good_channel if cid == 100 else bad_channel

    bot.get_channel = MagicMock(side_effect=get_channel_side_effect)

    refresher = FissureRefresher(bot)
    await refresher.tick()

    good_msg.edit.assert_awaited_once()
    assert bot.tracked_repo.deleted == [2]
