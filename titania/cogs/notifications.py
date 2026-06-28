from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from titania.presentation.filter_panel import FilterPanel

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
