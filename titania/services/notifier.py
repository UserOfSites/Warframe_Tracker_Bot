import asyncio
import logging
from typing import TYPE_CHECKING

import discord

from titania.domain.fissure import Fissure
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

    For each (guild_id, topic), keeps an in-memory set of fissure keys we've
    already handled. Each tick diffs the current matches against that set;
    freshly-appeared fissures trigger DMs to that guild's subscribers.

    On first call for a (guild, topic), the current state is captured
    silently — this avoids spamming users after a bot restart with DMs about
    already-active fissures they would have seen earlier.
    """

    def __init__(self, bot: "TitaniaBot") -> None:
        self._bot = bot
        self._seen: dict[tuple[int, str], set[tuple]] = {}

    async def process_guild(
        self,
        guild_id: int,
        all_fissures: list[Fissure],
        dojoshare_nodes: list[str],
    ) -> None:
        for topic in FissureTopic:
            current_matches = [
                f for f in all_fissures
                if fissure_matches_topic(f, topic, dojoshare_nodes)
            ]
            current_keys = {_fissure_key(f) for f in current_matches}
            seen_key = (guild_id, topic.value)
            previous = self._seen.get(seen_key)
            if previous is None:
                # First sighting for this (guild, topic) — capture state but
                # don't fire, to suppress restart noise.
                self._seen[seen_key] = current_keys
                continue
            new_keys = current_keys - previous
            if new_keys:
                new_fissures = [
                    f for f in current_matches if _fissure_key(f) in new_keys
                ]
                await self._dm_subscribers(guild_id, topic, new_fissures)
            self._seen[seen_key] = current_keys

    async def _dm_subscribers(
        self,
        guild_id: int,
        topic: FissureTopic,
        new_fissures: list[Fissure],
    ) -> None:
        user_ids = await self._bot.subscriptions_repo.list_subscribers(
            guild_id, topic.value
        )
        if not user_ids:
            return
        guild = self._bot.get_guild(guild_id)
        guild_name = guild.name if guild is not None else None
        log.info(
            "notifying %d subscriber(s) for guild=%s topic=%s (%d new fissure(s))",
            len(user_ids), guild_id, topic.value, len(new_fissures),
        )
        await asyncio.gather(
            *(
                self._dm_one_user(uid, topic, new_fissures, guild_name)
                for uid in user_ids
            ),
            return_exceptions=True,
        )

    async def _dm_one_user(
        self,
        user_id: int,
        topic: FissureTopic,
        new_fissures: list[Fissure],
        guild_name: str | None,
    ) -> None:
        try:
            user = self._bot.get_user(user_id) or await self._bot.fetch_user(user_id)
        except (discord.NotFound, discord.HTTPException):
            log.info("user %s not fetchable; skipping DM", user_id)
            return
        for f in new_fissures:
            embed = build_notification_embed(f, topic, guild_name=guild_name)
            try:
                await user.send(embed=embed)
            except discord.Forbidden:
                # User has DMs closed or has blocked the bot — give up on the
                # whole batch for this user, no point retrying.
                log.info("DM forbidden for user %s; skipping remaining", user_id)
                return
            except discord.HTTPException as e:
                log.warning("DM failed user=%s: %s", user_id, e)
