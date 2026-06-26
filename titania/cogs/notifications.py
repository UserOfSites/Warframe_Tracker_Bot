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

    @app_commands.command(
        name="notifications",
        description="Open the visual filter panel for your fissure subscriptions (DM only).",
    )
    async def notifications(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is not None:
            await interaction.response.send_message(
                "These are personal preferences — DM me and run `/notifications` "
                "there to manage them. Server-wide settings live under `/settings`.",
                ephemeral=True,
            )
            return
        panel = FilterPanel(_bot(interaction), interaction.user.id)
        await panel.open(interaction)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Notifications(bot))  # type: ignore[arg-type]
