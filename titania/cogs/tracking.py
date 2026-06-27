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

    @app_commands.guild_only()
    @app_commands.command(
        name="track",
        description="Auto-update an active-fissures embed in a channel.",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(channel="Channel or thread to post the auto-updating embed in.")
    async def track(  # noqa: D401  (error handler attached below)
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | discord.Thread,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        # Check we can actually post in the requested channel/thread. Threads
        # inherit ``permissions_for`` from the parent text channel, with an
        # extra ``send_messages_in_threads`` gate that applies to threads only.
        me = channel.guild.me
        perms = channel.permissions_for(me) if me else None
        needs_thread_perm = isinstance(channel, discord.Thread)
        if perms is None or not (
            perms.embed_links
            and perms.add_reactions
            and perms.read_message_history
            and (perms.send_messages_in_threads if needs_thread_perm else perms.send_messages)
        ):
            send_label = (
                "Send Messages in Threads" if needs_thread_perm else "Send Messages"
            )
            await interaction.response.send_message(
                f"I need **{send_label}**, **Embed Links**, **Add Reactions**, "
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

    @track.error
    async def _track_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Friendlier message for the most common /track failure mode.

        ``TransformerError`` on a channel parameter almost always means the
        bot couldn't promote the partial channel from the interaction payload
        to a real `TextChannel`/`Thread` — usually because it lacks View
        Channel permission there. The default error is opaque ("Failed to
        convert X to TextChannel or Thread"), so we translate it.
        """
        if isinstance(error, app_commands.TransformerError):
            value_name = getattr(error.value, "name", str(error.value))
            send = (
                interaction.followup.send
                if interaction.response.is_done()
                else interaction.response.send_message
            )
            await send(
                f"I can't access **{value_name}**. Most common cause: I don't "
                f"have **View Channel** permission on it.\n\n"
                f"Fix: open that channel → **Edit Channel** → **Permissions** "
                f"→ allow the bot (or its role) **View Channel** (and **Read "
                f"Message History**). Then try `/track` again.",
                ephemeral=True,
            )
            return
        # Re-raise anything else so the global handler still logs it.
        raise error

    @app_commands.guild_only()
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
