import logging
import re
from typing import TYPE_CHECKING

import discord

from titania.domain.topic import FissureTopic

if TYPE_CHECKING:
    from titania.bot import TitaniaBot

log = logging.getLogger(__name__)


# Registry key → topic. The bot seeds the tracked message with one reaction
# per entry, in this iteration order, so users see them in a stable layout.
_TOPIC_BY_EMOJI_KEY: dict[str, FissureTopic] = {
    "tenno": FissureTopic.NORMAL_FAST,
    "steel_path": FissureTopic.SP_FAST,
    "clan_xp": FissureTopic.DOJOSHARE,
    "omnia_relic": FissureTopic.SP_TUVUL_CASCADE,
}

# Unicode fallbacks per topic. Used if the matching application emoji isn't
# registered (asset missing, upload failed, etc.). The reaction listener also
# accepts these so subscribing keeps working even when custom icons aren't
# loaded — the bot just seeds and recognises the Unicode flavour instead.
_FALLBACK_UNICODE: dict[FissureTopic, str] = {
    FissureTopic.NORMAL_FAST: "⚡",
    FissureTopic.SP_FAST: "⚔️",
    FissureTopic.DOJOSHARE: "🏯",
    FissureTopic.SP_TUVUL_CASCADE: "🌀",
}

_EMOJI_MARKUP_RE = re.compile(r"<a?:[\w]+:(\d+)>")


def _emoji_id_from_markup(markup: str) -> int | None:
    """``'<:tenno:1234567890>'`` → ``1234567890``, otherwise ``None``."""
    if not markup:
        return None
    m = _EMOJI_MARKUP_RE.fullmatch(markup)
    return int(m.group(1)) if m else None


class ReactionSubscriber:
    """Maps reaction toggles on tracked fissure messages to topic subscriptions.

    Per-user state is rendered natively by Discord (your own reactions show
    highlighted; click again to remove). The bot seeds each tracker message
    with one reaction per topic so users have something to click; the seed
    reaction itself persists as long as the bot doesn't remove it, keeping
    the reaction row visible even when no users have subscribed.
    """

    def __init__(self, bot: "TitaniaBot") -> None:
        self._bot = bot
        self._topic_by_emoji_id: dict[int, FissureTopic] = {}
        self._topic_by_unicode: dict[str, FissureTopic] = {}

    def reload_emoji_map(self) -> None:
        """Rebuild the {emoji → topic} lookups from the live registry.
        Call after ``EmojiRegistry.sync`` so we know which IDs to listen for."""
        self._topic_by_emoji_id.clear()
        self._topic_by_unicode.clear()
        for key, topic in _TOPIC_BY_EMOJI_KEY.items():
            markup = self._bot.emoji_registry.get(key)
            eid = _emoji_id_from_markup(markup)
            if eid is not None:
                self._topic_by_emoji_id[eid] = topic
            else:
                # Custom emoji unavailable for this topic — fall back to
                # Unicode so the topic is still usable.
                self._topic_by_unicode[_FALLBACK_UNICODE[topic]] = topic

    def _emoji_for_topic(self, topic: FissureTopic) -> str | discord.PartialEmoji:
        """Custom emoji markup if registered, else the Unicode fallback."""
        markup = self._bot.emoji_registry.get(_emoji_key_for(topic))
        if markup:
            try:
                return discord.PartialEmoji.from_str(markup)
            except (ValueError, TypeError):
                pass
        return _FALLBACK_UNICODE[topic]

    async def seed_reactions(self, message: discord.Message) -> None:
        """Add one reaction per topic in deterministic order. Idempotent —
        Discord no-ops adding a reaction the bot already has."""
        for topic in FissureTopic:
            emoji = self._emoji_for_topic(topic)
            try:
                await message.add_reaction(emoji)
            except discord.Forbidden:
                log.warning(
                    "missing 'Add Reactions' / 'Read Message History' in "
                    "channel=%s; cannot seed reaction for %s",
                    message.channel.id, topic.value,
                )
                return
            except discord.HTTPException as e:
                log.warning("seed reaction failed for %s: %s", topic.value, e)

    def _topic_for_emoji(self, emoji: discord.PartialEmoji) -> FissureTopic | None:
        if emoji.id is not None:
            return self._topic_by_emoji_id.get(emoji.id)
        # Strip the variation selector (U+FE0F) that some clients append so
        # "⚔" and "⚔️" both match.
        name = (emoji.name or "").replace("️", "")
        for unicode_emoji, topic in self._topic_by_unicode.items():
            if unicode_emoji.replace("️", "") == name:
                return topic
        return None

    async def _is_tracker_message(self, guild_id: int, message_id: int) -> bool:
        tc = await self._bot.tracked_repo.get(guild_id)
        return tc is not None and tc.message_id == message_id

    async def handle_add(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        if self._bot.user is None or payload.user_id == self._bot.user.id:
            return  # the bot's own seed reaction
        if payload.guild_id is None:
            return
        if not await self._is_tracker_message(payload.guild_id, payload.message_id):
            return
        topic = self._topic_for_emoji(payload.emoji)
        if topic is None:
            # Foreign emoji on a tracker message — silently strip it so the
            # reaction row stays scoped to the 4 topic icons.
            await self._strip_foreign_reaction(payload)
            return
        try:
            await self._bot.subscriptions_repo.subscribe(
                payload.user_id, topic.value
            )
        except Exception:
            log.exception(
                "reaction-subscribe failed user=%s topic=%s",
                payload.user_id, topic.value,
            )

    async def _strip_foreign_reaction(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        """Remove a non-topic reaction from a tracker message.

        Requires Manage Messages in the channel; without it, the reaction
        stays and we log a one-line warning. Failures are otherwise swallowed
        — best-effort cleanup, not a critical path.
        """
        try:
            channel = self._bot.get_channel(payload.channel_id) or await self._bot.fetch_channel(payload.channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
        if not isinstance(channel, discord.abc.Messageable):
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
        user = self._bot.get_user(payload.user_id)
        if user is None:
            try:
                user = await self._bot.fetch_user(payload.user_id)
            except (discord.NotFound, discord.HTTPException):
                return
        try:
            await message.remove_reaction(payload.emoji, user)
        except discord.Forbidden:
            log.info(
                "missing Manage Messages in channel=%s; cannot strip foreign reaction",
                payload.channel_id,
            )
        except (discord.NotFound, discord.HTTPException) as e:
            log.warning("strip reaction failed: %s", e)

    async def handle_remove(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        if self._bot.user is None or payload.user_id == self._bot.user.id:
            return
        if payload.guild_id is None:
            return
        topic = self._topic_for_emoji(payload.emoji)
        if topic is None:
            return
        if not await self._is_tracker_message(payload.guild_id, payload.message_id):
            return
        try:
            await self._bot.subscriptions_repo.unsubscribe(
                payload.user_id, topic.value
            )
        except Exception:
            log.exception(
                "reaction-unsubscribe failed user=%s topic=%s",
                payload.user_id, topic.value,
            )


def _emoji_key_for(topic: FissureTopic) -> str:
    for key, t in _TOPIC_BY_EMOJI_KEY.items():
        if t is topic:
            return key
    raise KeyError(topic)
