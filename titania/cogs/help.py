from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from titania.bot import TitaniaBot


_PERSONAL_COMMANDS = (
    "**`/notifications`** — Open the visual filter panel: pick the topics you "
    "want, then set per-topic allowlists for planets, mission types, and "
    "specific nodes.\n"
    "**`/language`** — Set the language used in your DM notifications.\n"
    "**`/mute`** — Stop receiving notification DMs without losing your "
    "subscriptions.\n"
    "**`/unmute`** — Resume notification DMs.\n"
    "**`/cleanup`** — Wipe my recent state (summary + in-flight alerts) and "
    "immediately re-welcome + re-post a fresh summary.\n"
    "**`/wipe`** — Scorched earth: iterate our full DM history and delete "
    "every message I've ever sent. Stays silent until the next match."
)

_TRACKER_COMMANDS = (
    "**`/track #channel`** — Post an auto-updating fissures tracker in the "
    "channel; users react on its buttons to subscribe.\n"
    "**`/untrack`** — Remove the fissures tracker.\n"
    "**`/vendors track #channel`** — Post an auto-updating Baro Ki'Teer "
    "tracker.\n"
    "**`/vendors untrack`** — Remove the Baro tracker."
)

_SETTINGS_COMMANDS = (
    "**`/settings panel`** — Server-wide settings panel: which mission types "
    "appear on the tracker, the dojoshare node list, pinned (always-show) "
    "nodes, blocked (always-hide) nodes, and per-node quality stars "
    "(🌟 / ⭐).\n"
    "**`/settings language`** — Set the language used on the public trackers "
    "(fissures + Baro)."
)

_GENERAL_COMMANDS = (
    "**`/fissures`** — Show the currently-active fissures right now (one-off, "
    "no tracker).\n"
    "**`/vendors baro`** — Show Baro Ki'Teer's current status (countdown or "
    "live inventory).\n"
    "**`/ping`** — Check that I'm alive and view round-trip latency."
)

_SUBSCRIBE_FLOW = (
    "1. On a server with `/track` set up, click a reaction button on the "
    "tracker embed (⚡ Tenno = Normal Fast, Steel Essence = SP Fast, "
    "Clan XP = Dojoshare, Omnia = SP Tuvul Cascade).\n"
    "2. That topic is added to your subscriptions; you start receiving DM "
    "alerts and a persistent summary in our DMs.\n"
    "3. Optional: DM me `/notifications` to filter further (only certain "
    "planets, mission types, or specific nodes per topic).\n"
    "4. Click the same reaction again to unsubscribe — your filters are "
    "preserved for next time."
)


class Help(commands.Cog):
    """Single-command guide to every public Titania command."""

    def __init__(self, bot: "TitaniaBot") -> None:
        self.bot = bot

    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.command(
        name="help",
        description="Show the full list of commands and how they work.",
    )
    async def help_cmd(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="📖  StonksFox help",
            description=(
                "Below is every command grouped by where it lives. In a "
                "server, the slash-command picker hides anything you don't "
                "have permission to use."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="🔔  Personal  ·  use in DMs with me",
            value=_PERSONAL_COMMANDS,
            inline=False,
        )
        embed.add_field(
            name="📡  Server tracker  ·  Manage Server required",
            value=_TRACKER_COMMANDS,
            inline=False,
        )
        embed.add_field(
            name="⚙️  Server settings  ·  Manage Server required",
            value=_SETTINGS_COMMANDS,
            inline=False,
        )
        embed.add_field(
            name="📊  General  ·  usable anywhere",
            value=_GENERAL_COMMANDS,
            inline=False,
        )
        embed.add_field(
            name="❓  How do I subscribe to fissure notifications?",
            value=_SUBSCRIBE_FLOW,
            inline=False,
        )
        embed.set_footer(
            text="Server owners: per-command access can be customized in "
            "Server Settings → Integrations → StonksFox."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))  # type: ignore[arg-type]
