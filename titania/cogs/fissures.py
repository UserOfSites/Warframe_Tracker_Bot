from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from titania.bot import TitaniaBot


class Fissures(commands.Cog):
    def __init__(self, bot: "TitaniaBot") -> None:
        self.bot = bot

    @app_commands.guild_only()
    @app_commands.command(
        name="fissures",
        description="Show active Void Fissures (Normal · Steel Path · Dojoshare).",
    )
    async def fissures(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        embed = await self.bot.refresher.build_embed(interaction.guild_id)
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Fissures(bot))  # type: ignore[arg-type]
