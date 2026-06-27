import discord

from titania.domain.fissure import Fissure
from titania.domain.topic import FissureTopic, TOPIC_LABELS


def build_welcome_embed() -> discord.Embed:
    """One-off intro DM sent the first time a user subscribes (via reaction)
    or the first time a notification is about to be sent to them — whichever
    happens first."""
    embed = discord.Embed(
        title="👋  You're subscribed",
        description=(
            "I'll DM you here whenever a fissure matching one of your topic "
            "subscriptions goes live."
        ),
        color=discord.Color.green(),
    )
    embed.add_field(
        name="🛠  Manage preferences",
        value=(
            "Use `/notifications` in DMs with me to set per-topic filters "
            "(planets, mission types, specific nodes)."
        ),
        inline=False,
    )
    embed.add_field(
        name="❌  Unsubscribe a topic",
        value=(
            "Click the same reaction on the tracker embed again to remove it."
        ),
        inline=False,
    )
    embed.add_field(
        name="🧹  Auto-cleanup",
        value=(
            "Each notification is removed automatically once its fissure "
            "window expires, so your DM history stays clean."
        ),
        inline=False,
    )
    return embed


_TOPIC_COLOR: dict[FissureTopic, discord.Color] = {
    FissureTopic.NORMAL_FAST: discord.Color.blue(),
    FissureTopic.SP_FAST: discord.Color.dark_red(),
    FissureTopic.DOJOSHARE: discord.Color.green(),
    FissureTopic.SP_TUVUL_CASCADE: discord.Color.purple(),
}


def build_notification_embed(
    fissure: Fissure,
    topic: FissureTopic,
    *,
    guild_name: str | None = None,
) -> discord.Embed:
    """One DM embed per newly-active matching fissure.

    Self-contained — uses Discord timestamps for the relative-time so the
    embed stays accurate without needing translator/registry plumbing in the
    DM path.
    """
    embed = discord.Embed(
        title=f"⚡ {TOPIC_LABELS[topic]}",
        description=(
            "A matching fissure just went live"
            + (f" in **{guild_name}**." if guild_name else ".")
        ),
        color=_TOPIC_COLOR.get(topic, discord.Color.gold()),
    )
    embed.add_field(name="Era", value=fissure.era.value, inline=True)
    embed.add_field(name="Mission", value=fissure.mission_type.value, inline=True)
    embed.add_field(
        name="Mode",
        value="Steel Path" if fissure.is_steel_path else "Normal",
        inline=True,
    )
    location = f"{fissure.node} ({fissure.planet})" if fissure.planet else fissure.node
    embed.add_field(name="Node", value=location, inline=True)
    embed.add_field(
        name="Expires",
        value=f"<t:{int(fissure.expires_at.timestamp())}:R>",
        inline=True,
    )
    embed.set_footer(text="Click the button again on the tracker to unsubscribe.")
    return embed
