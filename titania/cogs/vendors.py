from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from titania.storage.tracked_channels_repo import TrackedChannel

if TYPE_CHECKING:
    from titania.bot import TitaniaBot


_OWNER_PERMS = discord.Permissions(manage_guild=True)


async def _safely_delete_message(
    bot: "TitaniaBot", channel_id: int, message_id: int
) -> None:
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        if isinstance(channel, discord.abc.Messageable):
            msg = await channel.fetch_message(message_id)
            await msg.delete()
    except (discord.NotFound, discord.Forbidden):
        pass


@app_commands.guild_only()
class Vendors(
    commands.GroupCog,
    name="vendors",
    description="Warframe vendor trackers (Baro Ki'Teer).",
):
    @app_commands.command(
        name="baro",
        description="Show Baro Ki'Teer's status (countdown or inventory).",
    )
    async def baro(self, interaction: discord.Interaction) -> None:
        bot: TitaniaBot = interaction.client  # type: ignore[assignment]
        await interaction.response.defer()
        embed = await bot.refresher.build_vendors_embed(interaction.guild_id)
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="track",
        description="Auto-update a vendors embed in a channel.",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(channel="Channel to post the auto-updating embed in.")
    async def track(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        bot: TitaniaBot = interaction.client  # type: ignore[assignment]
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        me = channel.guild.me
        perms = channel.permissions_for(me) if me else None
        if perms is None or not (perms.send_messages and perms.embed_links):
            await interaction.response.send_message(
                f"I need **Send Messages** and **Embed Links** in {channel.mention}.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        existing = await bot.tracked_vendors_repo.get(interaction.guild_id)
        if existing is not None:
            await _safely_delete_message(
                bot, existing.channel_id, existing.message_id
            )

        embed = await bot.refresher.build_vendors_embed(interaction.guild_id)
        posted = await channel.send(embed=embed)
        await bot.tracked_vendors_repo.upsert(
            TrackedChannel(
                guild_id=interaction.guild_id,
                channel_id=channel.id,
                message_id=posted.id,
            )
        )

        await interaction.followup.send(
            f"Tracking vendors in {channel.mention}. "
            f"The embed will refresh every ~{int(bot.config.fissure_cache_ttl)}s.",
            ephemeral=True,
        )

    @app_commands.command(
        name="untrack",
        description="Stop auto-updating the vendors embed.",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def untrack(self, interaction: discord.Interaction) -> None:
        bot: TitaniaBot = interaction.client  # type: ignore[assignment]
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        tc = await bot.tracked_vendors_repo.get(interaction.guild_id)
        if tc is None:
            await interaction.response.send_message(
                "No tracked vendors channel for this server.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        await _safely_delete_message(bot, tc.channel_id, tc.message_id)
        await bot.tracked_vendors_repo.delete(interaction.guild_id)
        await interaction.followup.send("Vendor tracking stopped.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Vendors(bot))  # type: ignore[arg-type]
