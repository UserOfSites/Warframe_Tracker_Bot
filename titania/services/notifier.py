import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord

from titania.domain.fissure import Fissure
from titania.domain.mission_type import DEFAULT_DOJOSHARE_NODES
from titania.domain.subscription_filter import SubscriptionFilter
from titania.domain.topic import FissureTopic, fissure_matches_topic
from titania.presentation.notification_embed import (
    build_alert_text,
    build_user_summary_embed,
    build_welcome_embed,
)

if TYPE_CHECKING:
    from titania.bot import TitaniaBot

log = logging.getLogger(__name__)


def _fissure_key(f: Fissure) -> tuple:
    """Stable identity for a fissure window — used for dedup across ticks."""
    return (f.era.value, f.node, f.is_steel_path, f.expires_at.isoformat())


@dataclass
class _AlertEntry:
    """A short text DM that pings the user about a freshly-active fissure.
    Deleted automatically once the latest fissure it covered has expired,
    so the user's history stays clean even across restarts (the summary
    message picks up the slack — see ``UserNotificationMessagesRepository``)."""

    message: discord.Message
    expires_at: datetime


class FissureNotifier:
    """Per-user persistent-summary DM + short alerts.

    The model is *one tracker-like message per user* — a persistent embed
    that the notifier edits in place as the user's matching fissures appear
    and expire. New matches trigger a brief text alert; the alert deletes
    itself when its underlying fissures expire.

    State:
      - ``_user_seen[user_id]``: the set of fissure keys we showed the user
        last tick. Diffing against the current matches tells us what's new
        and whether we need to re-edit the summary.
      - ``_alerts[user_id]``: in-flight short alert messages awaiting cleanup
        on fissure expiry.
      - ``_welcomed``: one-shot welcome dedup (per process).

    Summary message persistence lives in the DB
    (``user_notification_messages``) so restarts pick up where we left off
    instead of orphaning a stale message and posting a fresh one above it.
    """

    def __init__(self, bot: "TitaniaBot") -> None:
        self._bot = bot
        self._user_seen: dict[int, set[tuple]] = {}
        self._alerts: dict[int, list[_AlertEntry]] = {}
        self._welcomed: set[int] = set()

    # ---------- public entry points ----------

    async def maybe_welcome(self, user_id: int) -> None:
        """Send the welcome DM if we haven't yet (idempotent per process)."""
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
        # Sweep expired alerts first so the channel breathes before we possibly
        # post fresh ones below.
        await self._cleanup_expired_alerts()

        user_subs = await self._collect_user_subscriptions()
        for user_id, subs in user_subs.items():
            try:
                await self._process_user(user_id, subs, all_fissures)
            except Exception:
                log.exception("notifier failed for user=%s", user_id)

    # ---------- per-user driver ----------

    async def _process_user(
        self,
        user_id: int,
        subs: list[tuple[FissureTopic, SubscriptionFilter]],
        all_fissures: list[Fissure],
    ) -> None:
        matches_by_topic = self._matches_for_user(subs, all_fissures)
        current_keys = {
            _fissure_key(f)
            for fissures in matches_by_topic.values()
            for f in fissures
        }
        previous = self._user_seen.get(user_id)

        if previous is None:
            # First sighting — silently baseline so a restart doesn't fire
            # alerts for fissures the user already saw.
            self._user_seen[user_id] = current_keys
            if current_keys:
                await self.maybe_welcome(user_id)
                await self._upsert_summary(user_id, matches_by_topic)
            return

        if current_keys != previous:
            await self._upsert_summary(user_id, matches_by_topic)

        new_keys = current_keys - previous
        if new_keys:
            new_fissures = [
                f
                for fissures in matches_by_topic.values()
                for f in fissures
                if _fissure_key(f) in new_keys
            ]
            # Don't re-dispatch the same fissure twice if it matches multiple
            # of the user's topics.
            seen_keys: set[tuple] = set()
            deduped: list[Fissure] = []
            for f in new_fissures:
                k = _fissure_key(f)
                if k in seen_keys:
                    continue
                seen_keys.add(k)
                deduped.append(f)
            await self._send_alert(user_id, deduped)

        self._user_seen[user_id] = current_keys

    # ---------- query helpers ----------

    async def _collect_user_subscriptions(
        self,
    ) -> dict[int, list[tuple[FissureTopic, SubscriptionFilter]]]:
        """Invert the per-topic subscriber list into per-user."""
        result: dict[int, list[tuple[FissureTopic, SubscriptionFilter]]] = {}
        for topic in FissureTopic:
            subs = await self._bot.subscriptions_repo.list_subscribers_with_filters(
                topic.value
            )
            for user_id, filt in subs:
                result.setdefault(user_id, []).append((topic, filt))
        return result

    def _matches_for_user(
        self,
        subs: list[tuple[FissureTopic, SubscriptionFilter]],
        all_fissures: list[Fissure],
    ) -> dict[FissureTopic, list[Fissure]]:
        """Group the user's matching fissures by topic, applying their
        per-topic allowlist filter."""
        out: dict[FissureTopic, list[Fissure]] = {}
        for topic, filt in subs:
            matched = [
                f
                for f in all_fissures
                if fissure_matches_topic(f, topic, DEFAULT_DOJOSHARE_NODES)
                and (filt.is_unrestricted or filt.matches(f))
            ]
            if matched:
                out[topic] = matched
        return out

    # ---------- summary message ----------

    async def _upsert_summary(
        self,
        user_id: int,
        matches_by_topic: dict[FissureTopic, list[Fissure]],
    ) -> None:
        """Edit the user's persistent summary message in place, creating one
        if it doesn't exist yet."""
        embed = build_user_summary_embed(matches_by_topic, self._bot.emoji_registry)

        existing = await self._bot.user_notification_messages_repo.get(user_id)
        if existing is not None:
            channel_id, message_id = existing
            if await self._try_edit_summary(channel_id, message_id, embed):
                return
            # Edit failed (message gone). Drop the stale record so we create
            # a fresh one below.
            await self._bot.user_notification_messages_repo.delete(user_id)

        await self._create_summary(user_id, embed)

    async def _try_edit_summary(
        self, channel_id: int, message_id: int, embed: discord.Embed
    ) -> bool:
        try:
            channel = (
                self._bot.get_channel(channel_id)
                or await self._bot.fetch_channel(channel_id)
            )
            if not isinstance(channel, discord.abc.Messageable):
                return False
            msg = await channel.fetch_message(message_id)
            await msg.edit(embed=embed)
            return True
        except (discord.NotFound, discord.Forbidden):
            return False
        except discord.HTTPException as e:
            log.warning("summary edit failed: %s", e)
            return False

    async def _create_summary(self, user_id: int, embed: discord.Embed) -> None:
        try:
            user = self._bot.get_user(user_id) or await self._bot.fetch_user(user_id)
        except (discord.NotFound, discord.HTTPException):
            log.info("user %s not fetchable; cannot create summary", user_id)
            return
        try:
            sent = await user.send(embed=embed)
        except discord.Forbidden:
            log.info("DM forbidden for user %s; cannot create summary", user_id)
            return
        except discord.HTTPException as e:
            log.warning("summary create failed user=%s: %s", user_id, e)
            return
        await self._bot.user_notification_messages_repo.upsert(
            user_id, sent.channel.id, sent.id
        )

    # ---------- alerts ----------

    async def _send_alert(
        self, user_id: int, new_fissures: list[Fissure]
    ) -> None:
        if not new_fissures:
            return
        try:
            user = self._bot.get_user(user_id) or await self._bot.fetch_user(user_id)
        except (discord.NotFound, discord.HTTPException):
            return
        text = build_alert_text(new_fissures)
        try:
            sent = await user.send(text)
        except discord.Forbidden:
            log.info("alert DM forbidden for user %s", user_id)
            return
        except discord.HTTPException as e:
            log.warning("alert DM failed user=%s: %s", user_id, e)
            return
        # Auto-delete when the LAST of the covered fissures expires — that's
        # the moment the alert text becomes stale.
        latest_expiry = max(f.expires_at for f in new_fissures)
        self._alerts.setdefault(user_id, []).append(
            _AlertEntry(message=sent, expires_at=latest_expiry)
        )

    async def _cleanup_expired_alerts(self) -> None:
        now = datetime.now(timezone.utc)
        for user_id, alerts in list(self._alerts.items()):
            still_active: list[_AlertEntry] = []
            for entry in alerts:
                if entry.expires_at <= now:
                    try:
                        await entry.message.delete()
                    except discord.NotFound:
                        pass
                    except discord.Forbidden:
                        log.info(
                            "alert delete forbidden for message %s", entry.message.id
                        )
                    except discord.HTTPException as e:
                        log.warning("alert delete failed: %s", e)
                else:
                    still_active.append(entry)
            if still_active:
                self._alerts[user_id] = still_active
            else:
                del self._alerts[user_id]
