from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from titania.storage.tracked_channels_repo import TrackedChannel

if TYPE_CHECKING:
    from titania.bot import TitaniaBot


_OWNER_PERMS = discord.Permissions(manage_guild=True)


class Tracking(commands.Cog):
    def __init__(self, bot: "TitaniaBot") -> None:
        self.bot = bot

    @app_commands.command(
        name="track",
        description="Auto-update an active-fissures embed in a channel.",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(channel="Channel to post the auto-updating embed in.")
    async def track(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        # Check we can actually post in the requested channel.
        me = channel.guild.me
        perms = channel.permissions_for(me) if me else None
        if perms is None or not (
            perms.send_messages
            and perms.embed_links
            and perms.add_reactions
            and perms.read_message_history
        ):
            await interaction.response.send_message(
                f"I need **Send Messages**, **Embed Links**, **Add Reactions**, "
                f"and **Read Message History** in {channel.mention}.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Clean up any previous tracked message for this guild.
        existing = await self.bot.tracked_repo.get(interaction.guild_id)
        if existing is not None:
            await _safely_delete_message(
                self.bot, existing.channel_id, existing.message_id
            )

        embed = await self.bot.refresher.build_embed(interaction.guild_id)
        posted = await channel.send(embed=embed)
        await self.bot.tracked_repo.upsert(
            TrackedChannel(
                guild_id=interaction.guild_id,
                channel_id=channel.id,
                message_id=posted.id,
            )
        )
        # Seed one reaction per topic so users have something to click to
        # subscribe. The bot's reaction acts as a permanent placeholder; users
        # toggle by clicking the count.
        await self.bot.reaction_subscriber.seed_reactions(posted)

        await interaction.followup.send(
            f"Tracking active fissures in {channel.mention}. "
            f"The embed will refresh every ~{int(self.bot.config.fissure_cache_ttl)}s.",
            ephemeral=True,
        )

    @app_commands.command(
        name="untrack",
        description="Stop auto-updating the fissures embed.",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def untrack(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        tc = await self.bot.tracked_repo.get(interaction.guild_id)
        if tc is None:
            await interaction.response.send_message(
                "No tracked channel for this server.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        await _safely_delete_message(self.bot, tc.channel_id, tc.message_id)
        await self.bot.tracked_repo.delete(interaction.guild_id)
        await interaction.followup.send("Tracking stopped.", ephemeral=True)


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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tracking(bot))  # type: ignore[arg-type]
