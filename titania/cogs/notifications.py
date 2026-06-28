import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from titania.presentation.filter_panel import FilterPanel

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from titania.bot import TitaniaBot


def _bot(interaction: discord.Interaction) -> "TitaniaBot":
    return interaction.client  # type: ignore[return-value]


class Notifications(commands.Cog):
    """DM-only entry point for managing your fissure-subscription filters.

    Notification preferences are personal — they don't make sense to set in a
    public server channel — so this cog rejects guild-context invocations and
    points users at their DMs with the bot instead. Subscribing itself still
    happens in the guild via the reactions on the fissure tracker; this cog
    edits the per-(user, topic) allowlist filter layered on top.
    """

    def __init__(self, bot: "TitaniaBot") -> None:
        self.bot = bot

    # Discord 2024 context model: by default, slash commands appear in
    # guilds and DMs sharing a server with the bot. We explicitly opt out of
    # guild context and into DMs (both bot DMs and the user's private channels)
    # so the command is only offered in personal chat. ``allowed_installs``
    # keeps the standard guild-install — no user-install required.
    @app_commands.allowed_contexts(guilds=False, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.command(
        name="notifications",
        description="Open the visual filter panel for your fissure subscriptions (DM only).",
    )
    async def notifications(self, interaction: discord.Interaction) -> None:
        # Defensive: if Discord ever loosens context filtering, we still
        # refuse server invocations.
        if interaction.guild_id is not None:
            await interaction.response.send_message(
                "These are personal preferences — DM me and run `/notifications` "
                "there to manage them. Server-wide settings live under `/settings`.",
                ephemeral=True,
            )
            return
        panel = FilterPanel(_bot(interaction), interaction.user.id)
        await panel.open(interaction)

    @app_commands.allowed_contexts(guilds=False, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.command(
        name="cleanup",
        description="Delete your notification history with me and start fresh (DM only).",
    )
    async def cleanup(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is not None:
            await interaction.response.send_message(
                "DM me to clean up your notification history.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await self.bot.notifier.cleanup_user(interaction.user.id)
        except Exception:
            await interaction.followup.send(
                "Couldn't fully clean up — some messages may be gone already. "
                "Try again if anything still looks wrong.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            "🧹 Cleared your notification history. Your subscriptions and "
            "filter preferences are unchanged — I'll post a fresh summary the "
            "next time a matching fissure goes live.",
            ephemeral=True,
        )

    @app_commands.allowed_contexts(guilds=False, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.command(
        name="mute",
        description="Stop receiving notification DMs (subscriptions kept). DM only.",
    )
    async def mute(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is not None:
            await interaction.response.send_message(
                "DM me to mute notifications.", ephemeral=True
            )
            return
        await self.bot.user_preferences_repo.set_muted(interaction.user.id, True)
        await interaction.response.send_message(
            "🔕 Muted. I'll stop posting summary updates and alerts to you. "
            "Use `/unmute` to resume — your subscriptions and filters stay "
            "exactly as they are.",
            ephemeral=True,
        )

    @app_commands.allowed_contexts(guilds=False, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.command(
        name="wipe",
        description="Delete every message I've ever sent in our DM history (DM only).",
    )
    async def wipe(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is not None:
            await interaction.response.send_message(
                "DM me to wipe our chat history.", ephemeral=True
            )
            return
        # History iteration + N sequential deletes can take a moment; defer
        # right away so the interaction token doesn't time out.
        await interaction.response.defer(ephemeral=True, thinking=True)

        channel = interaction.channel
        if not isinstance(channel, discord.DMChannel):
            try:
                channel = await interaction.user.create_dm()
            except discord.HTTPException:
                log.exception(
                    "wipe: could not open DM channel for user=%s",
                    interaction.user.id,
                )
                await interaction.followup.send(
                    "Couldn't open our DM channel — try again in a moment.",
                    ephemeral=True,
                )
                return

        bot_user = self.bot.user
        if bot_user is None:
            await interaction.followup.send(
                "Bot identity missing — try again in a moment.",
                ephemeral=True,
            )
            return

        deleted = 0
        try:
            async for msg in channel.history(limit=None):
                if msg.author.id != bot_user.id:
                    continue
                try:
                    await msg.delete()
                    deleted += 1
                except discord.NotFound:
                    pass  # already gone, no-op
                except discord.Forbidden:
                    log.info(
                        "wipe: forbidden to delete message %s in DM with %s",
                        msg.id, interaction.user.id,
                    )
                except discord.HTTPException as e:
                    log.warning("wipe: delete %s failed: %s", msg.id, e)
        except discord.HTTPException:
            log.exception(
                "wipe: history iteration failed for user=%s", interaction.user.id
            )

        # Reset in-memory tracking + DB record without re-welcoming or re-
        # creating the summary — the user asked for silence, not a fresh
        # start. The next matching fissure will naturally re-welcome.
        try:
            await self.bot.notifier.cleanup_user(
                interaction.user.id, recreate=False
            )
        except Exception:
            log.exception(
                "wipe: cleanup_user failed for user=%s", interaction.user.id
            )

        await interaction.followup.send(
            f"🧹 Wiped **{deleted}** of my messages from our DMs. "
            "Your subscriptions and filters are unchanged — the next matching "
            "fissure will re-welcome you and post a fresh summary.",
            ephemeral=True,
        )

    @app_commands.allowed_contexts(guilds=False, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.command(
        name="unmute",
        description="Resume receiving notification DMs. DM only.",
    )
    async def unmute(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is not None:
            await interaction.response.send_message(
                "DM me to unmute notifications.", ephemeral=True
            )
            return
        await self.bot.user_preferences_repo.set_muted(interaction.user.id, False)
        # Forget what we last showed so the next tick re-baselines silently —
        # avoids dumping every currently-active fissure as a "new" alert.
        self.bot.notifier.reset_seen(interaction.user.id)
        await interaction.response.send_message(
            "🔔 Unmuted. I'll resume posting your summary and alerts. The "
            "next post will be a fresh summary of what's currently active — "
            "no spammy backlog of alerts for fissures already in flight.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Notifications(bot))  # type: ignore[arg-type]
