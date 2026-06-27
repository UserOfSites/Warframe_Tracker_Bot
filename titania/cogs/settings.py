from dataclasses import replace
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from titania.presentation.settings_panel import SettingsPanel
from titania.services.guild_settings import GuildSettings  # noqa: F401

if TYPE_CHECKING:
    from titania.bot import TitaniaBot


_OWNER_PERMS = discord.Permissions(manage_guild=True)


async def _require_guild(interaction: discord.Interaction) -> int | None:
    """Settings only make sense inside a guild. Return guild_id or send an
    error and return None."""
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "Settings can only be configured in a server, not in DMs.",
            ephemeral=True,
        )
        return None
    return interaction.guild_id


def _bot(interaction: discord.Interaction) -> "TitaniaBot":
    return interaction.client  # type: ignore[return-value]


@app_commands.guild_only()
class Settings(
    commands.GroupCog,
    name="settings",
    description="Per-guild bot configuration (Manage Guild required).",
):
    """Server-side settings cog.

    All node/mission management runs through ``/settings panel`` now — a
    point-and-click view that mirrors the user-facing notifications panel.
    The only standalone slash command kept here is ``/settings language``,
    which is a single-value enum and didn't benefit from the visual UI.
    """

    @app_commands.command(
        name="panel",
        description="Open the visual server-settings panel (Manage Guild required).",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def panel(self, interaction: discord.Interaction) -> None:
        guild_id = await _require_guild(interaction)
        if guild_id is None:
            return
        panel = SettingsPanel(_bot(interaction), guild_id)
        await panel.open(interaction)

    @app_commands.command(
        name="language",
        description="Set the guild's UI language.",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.choices(
        lang=[
            app_commands.Choice(name="English", value="en"),
            app_commands.Choice(name="Italiano", value="it"),
        ]
    )
    async def language(
        self,
        interaction: discord.Interaction,
        lang: app_commands.Choice[str],
    ) -> None:
        guild_id = await _require_guild(interaction)
        if guild_id is None:
            return
        bot = _bot(interaction)
        current = await bot.settings_repo.get(guild_id)
        new = replace(current, locale=lang.value)
        await bot.settings_repo.save(guild_id, new)
        await interaction.response.send_message(
            f"Language set to **{lang.name}**.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Settings(bot))  # type: ignore[arg-type]
