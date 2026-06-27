from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from titania.bot import TitaniaBot


def _bot(interaction: discord.Interaction) -> "TitaniaBot":
    return interaction.client  # type: ignore[return-value]


_LANG_CHOICES = [
    app_commands.Choice(name="English", value="en"),
    app_commands.Choice(name="Italiano", value="it"),
]


class Language(commands.Cog):
    """DM-only command for users to set their personal locale. Applies to
    the DM notification embeds and the welcome embed. Guild-wide language
    stays under ``/settings panel`` for server owners."""

    def __init__(self, bot: "TitaniaBot") -> None:
        self.bot = bot

    @app_commands.allowed_contexts(guilds=False, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.command(
        name="language",
        description="Set your personal language for DM notifications.",
    )
    @app_commands.choices(lang=_LANG_CHOICES)
    async def language(
        self,
        interaction: discord.Interaction,
        lang: app_commands.Choice[str],
    ) -> None:
        if interaction.guild_id is not None:
            await interaction.response.send_message(
                "This is a personal preference — DM me to use it.",
                ephemeral=True,
            )
            return
        await self.bot.user_preferences_repo.set_locale(
            interaction.user.id, lang.value
        )
        await interaction.response.send_message(
            f"Language set to **{lang.name}** for your DM notifications.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Language(bot))  # type: ignore[arg-type]
