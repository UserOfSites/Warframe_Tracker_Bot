import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord

from titania.domain.fissure import Fissure
from titania.domain.mission_type import DEFAULT_DOJOSHARE_NODES
from titania.domain.topic import FissureTopic, fissure_matches_topic
from titania.presentation.notification_embed import (
    build_notification_embed,
    build_welcome_embed,
)

if TYPE_CHECKING:
    from titania.bot import TitaniaBot

log = logging.getLogger(__name__)


def _fissure_key(f: Fissure) -> tuple:
    """Stable identity for a fissure window — used for dedup across ticks."""
    return (f.era.value, f.node, f.is_steel_path, f.expires_at.isoformat())


@dataclass
class _SentBatch:
    """All DMs sent for one fissure window, kept in memory so we can delete
    them after the fissure expires. Bot restarts forfeit the cleanup for any
    DMs sent before the restart — those just linger in the user's DM history
    until manually cleared. Trade-off: avoiding DB persistence for short-lived
    state."""

    expires_at: datetime
    messages: list[discord.Message] = field(default_factory=list)


class FissureNotifier:
    """Edge-triggered DM dispatch for per-topic fissure subscriptions.

    Subscriptions are global per user; so is the notifier — one pass per
    tick, one DM per (user, freshly-active matching fissure). Per-(topic)
    in-memory seen-set dedups across ticks; first sighting captures state
    silently to avoid restart spam.

    Two QoL behaviours layered on top:
      - **Auto-cleanup**: messages are tracked by fissure key and deleted
        once the fissure window expires, so users don't accumulate stale
        DMs in their inbox.
      - **One-shot welcome**: the first time we send (or are about to send)
        anything to a given user, we precede it with a short welcome embed
        explaining the system. Tracked in-memory; a restart re-greets
        previously-welcomed users.
    """

    def __init__(self, bot: "TitaniaBot") -> None:
        self._bot = bot
        self._seen: dict[str, set[tuple]] = {}
        self._sent: dict[tuple, _SentBatch] = {}
        self._welcomed: set[int] = set()

    async def maybe_welcome(self, user_id: int) -> None:
        """Send the welcome DM if we haven't yet. Idempotent within a single
        process lifetime — the user receives at most one welcome per restart.
        Failures (DMs blocked, user not fetchable) are swallowed; we still
        mark the user as welcomed so we don't retry on every interaction."""
        if user_id in self._welcomed:
            return
        self._welcomed.add(user_id)
        try:
            user = self._bot.get_user(user_id) or await self._bot.fetch_user(user_id)
        except (discord.NotFound, discord.HTTPException) as e:
            log.info("welcome DM: user %s not fetchable (%s)", user_id, e)
            return
        try:
            await user.send(embed=build_welcome_embed())
        except discord.Forbidden:
            log.info("welcome DM forbidden for user %s", user_id)
        except discord.HTTPException as e:
            log.warning("welcome DM failed user=%s: %s", user_id, e)

    async def process(self, all_fissures: list[Fissure]) -> None:
        # Cleanup runs first so a fast tick after a fissure expires gets the
        # delete in promptly. The current `all_fissures` are unused for
        # cleanup — we use the recorded expires_at from when the DM was sent.
        await self._cleanup_expired_dms()

        for topic in FissureTopic:
            current_matches = [
                f for f in all_fissures
                if fissure_matches_topic(f, topic, DEFAULT_DOJOSHARE_NODES)
            ]
            current_keys = {_fissure_key(f) for f in current_matches}
            previous = self._seen.get(topic.value)
            if previous is None:
                self._seen[topic.value] = current_keys
                continue
            new_keys = current_keys - previous
            if new_keys:
                new_fissures = [
                    f for f in current_matches if _fissure_key(f) in new_keys
                ]
                await self._dm_subscribers(topic, new_fissures)
            self._seen[topic.value] = current_keys

    async def _cleanup_expired_dms(self) -> None:
        """Delete any tracked DM whose fissure window has expired."""
        now = datetime.now(timezone.utc)
        expired_keys = [k for k, batch in self._sent.items() if batch.expires_at <= now]
        if not expired_keys:
            return
        total = sum(len(self._sent[k].messages) for k in expired_keys)
        log.info(
            "cleaning %d expired DM(s) across %d fissure window(s)",
            total, len(expired_keys),
        )
        for key in expired_keys:
            batch = self._sent.pop(key)
            for msg in batch.messages:
                try:
                    await msg.delete()
                except discord.NotFound:
                    pass  # user already deleted it — fine
                except discord.Forbidden:
                    # Lost the ability to delete (rare in DMs); give up on
                    # this one, the rest of the batch can still proceed.
                    log.info("DM delete forbidden for message %s", msg.id)
                except discord.HTTPException as e:
                    log.warning("DM delete failed: %s", e)

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
        await self.maybe_welcome(user_id)
        try:
            user = self._bot.get_user(user_id) or await self._bot.fetch_user(user_id)
        except (discord.NotFound, discord.HTTPException):
            log.info("user %s not fetchable; skipping DM", user_id)
            return
        for f in new_fissures:
            embed = build_notification_embed(f, topic)
            try:
                sent = await user.send(embed=embed)
            except discord.Forbidden:
                # User has DMs closed or has blocked the bot — give up on the
                # whole batch for this user, no point retrying.
                log.info("DM forbidden for user %s; skipping remaining", user_id)
                return
            except discord.HTTPException as e:
                log.warning("DM failed user=%s: %s", user_id, e)
                continue

            key = _fissure_key(f)
            batch = self._sent.get(key)
            if batch is None:
                batch = _SentBatch(expires_at=f.expires_at)
                self._sent[key] = batch
            batch.messages.append(sent)
