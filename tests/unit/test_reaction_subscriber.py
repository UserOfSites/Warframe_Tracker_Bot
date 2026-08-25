from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from titania.services.emoji_registry import EmojiRegistry
from titania.services.reaction_subscriber import ReactionSubscriber
from titania.storage.tracked_channels_repo import TrackedChannel


class _FakeBot:
    def __init__(self, tracker: TrackedChannel | None):
        self._tracker = tracker
        self.emoji_registry = EmojiRegistry()  # empty -> Unicode fallbacks seed
        self.tracked_repo = MagicMock()
        self.tracked_repo.get = AsyncMock(return_value=tracker)
        self.message = MagicMock()
        self.message.add_reaction = AsyncMock()
        channel = MagicMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(return_value=self.message)
        self.get_channel = MagicMock(return_value=channel)
        self.fetch_channel = AsyncMock(return_value=channel)


def _clear_payload(guild_id=1, channel_id=100, message_id=200):
    # RawReactionClearEvent exposes guild_id/channel_id/message_id — enough for
    # handle_clear.
    return SimpleNamespace(guild_id=guild_id, channel_id=channel_id, message_id=message_id)


async def test_clear_reseeds_the_tracker_icons():
    tracker = TrackedChannel(guild_id=1, channel_id=100, message_id=200)
    bot = _FakeBot(tracker)
    sub = ReactionSubscriber(bot)

    await sub.handle_clear(_clear_payload())

    # One reaction seeded per topic (Unicode fallbacks, registry is empty).
    from titania.domain.topic import FissureTopic
    assert bot.message.add_reaction.await_count == len(list(FissureTopic))


async def test_clear_ignored_when_not_a_tracker_message():
    tracker = TrackedChannel(guild_id=1, channel_id=100, message_id=200)
    bot = _FakeBot(tracker)
    sub = ReactionSubscriber(bot)

    # Different message id -> not the tracker -> no reseed.
    await sub.handle_clear(_clear_payload(message_id=999))
    bot.message.add_reaction.assert_not_awaited()


async def test_clear_ignored_outside_a_guild():
    bot = _FakeBot(None)
    sub = ReactionSubscriber(bot)
    await sub.handle_clear(_clear_payload(guild_id=None))
    bot.message.add_reaction.assert_not_awaited()
