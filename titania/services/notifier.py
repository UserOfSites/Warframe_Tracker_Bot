import asyncio
import logging
from typing import TYPE_CHECKING

import discord

from titania.domain.fissure import Fissure
from titania.domain.mission_type import DEFAULT_DOJOSHARE_NODES
from titania.domain.topic import FissureTopic, fissure_matches_topic
from titania.presentation.notification_embed import build_notification_embed

if TYPE_CHECKING:
    from titania.bot import TitaniaBot

log = logging.getLogger(__name__)


def _fissure_key(f: Fissure) -> tuple:
    """Stable identity for a fissure window — used for dedup across ticks."""
    return (f.era.value, f.node, f.is_steel_path, f.expires_at.isoformat())


class FissureNotifier:
    """Edge-triggered DM dispatch for per-topic fissure subscriptions.

    Subscriptions are global per user; so is the notifier — one pass per
    tick, one DM per (user, freshly-active matching fissure). Per-(topic)
    in-memory seen-set dedups across ticks; first sighting captures state
    silently to avoid restart spam.

    The dojoshare topic predicate needs a list of dojoshare nodes; since
    subscriptions are global, we feed it the bot-wide default constant
    rather than any single guild's setting.
    """

    def __init__(self, bot: "TitaniaBot") -> None:
        self._bot = bot
        self._seen: dict[str, set[tuple]] = {}

    async def process(self, all_fissures: list[Fissure]) -> None:
        for topic in FissureTopic:
            current_matches = [
                f for f in all_fissures
                if fissure_matches_topic(f, topic, DEFAULT_DOJOSHARE_NODES)
            ]
            current_keys = {_fissure_key(f) for f in current_matches}
            previous = self._seen.get(topic.value)
            if previous is None:
                # First sighting for this topic — capture state but don't fire,
                # to suppress restart noise.
                self._seen[topic.value] = current_keys
                continue
            new_keys = current_keys - previous
            if new_keys:
                new_fissures = [
                    f for f in current_matches if _fissure_key(f) in new_keys
                ]
                await self._dm_subscribers(topic, new_fissures)
            self._seen[topic.value] = current_keys

    async def _dm_subscribers(
        self, topic: FissureTopic, new_fissures: list[Fissure]
    ) -> None:
        subs = await self._bot.subscriptions_repo.list_subscribers_with_filters(
            topic.value
        )
        if not subs:
            return
        log.info(
            "notifying %d subscriber(s) for topic=%s (%d new fissure(s))",
            len(subs), topic.value, len(new_fissures),
        )

        async def _dispatch(user_id: int, sub_filter) -> None:
            personal = (
                new_fissures
                if sub_filter.is_unrestricted
                else [f for f in new_fissures if sub_filter.matches(f)]
            )
            if not personal:
                return
            await self._dm_one_user(user_id, topic, personal)

        await asyncio.gather(
            *(_dispatch(uid, f) for uid, f in subs),
            return_exceptions=True,
        )

    async def _dm_one_user(
        self,
        user_id: int,
        topic: FissureTopic,
        new_fissures: list[Fissure],
    ) -> None:
        try:
            user = self._bot.get_user(user_id) or await self._bot.fetch_user(user_id)
        except (discord.NotFound, discord.HTTPException):
            log.info("user %s not fetchable; skipping DM", user_id)
            return
        for f in new_fissures:
            embed = build_notification_embed(f, topic)
            try:
                await user.send(embed=embed)
            except discord.Forbidden:
                # User has DMs closed or has blocked the bot — give up on the
                # whole batch for this user, no point retrying.
                log.info("DM forbidden for user %s; skipping remaining", user_id)
                return
            except discord.HTTPException as e:
                log.warning("DM failed user=%s: %s", user_id, e)
