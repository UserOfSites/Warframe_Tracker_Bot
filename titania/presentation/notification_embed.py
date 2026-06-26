import discord

from titania.domain.fissure import Fissure
from titania.domain.topic import FissureTopic, TOPIC_LABELS


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
