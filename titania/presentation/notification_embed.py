import discord

from titania.domain.era import Era
from titania.domain.fissure import Fissure
from titania.domain.topic import FissureTopic, TOPIC_LABELS
from titania.services.emoji_registry import EmojiRegistry


_ERA_EMOJI_KEY: dict[Era, str] = {
    Era.LITH: "lith_relic",
    Era.MESO: "meso_relic",
    Era.NEO: "neo_relic",
    Era.AXI: "axi_relic",
    Era.OMNIA: "omnia_relic",
}


def _era_marker(era: Era, is_sp: bool, registry: EmojiRegistry) -> str:
    era_emoji = registry.get(_ERA_EMOJI_KEY.get(era, ""), era.value)
    if not is_sp:
        return era_emoji
    sp_emoji = registry.get("steel_path", "[SP] ")
    return f"{sp_emoji}{era_emoji}"


def _fissure_row(f: Fissure, registry: EmojiRegistry) -> str:
    marker = _era_marker(f.era, f.is_steel_path, registry)
    location = f"{f.node} ({f.planet})" if f.planet else f.node
    ts = f"<t:{int(f.expires_at.timestamp())}:R>"
    return f"{marker} **{f.era.value}**  {f.mission_type.value} — {location}  {ts}"


def build_user_summary_embed(
    matches_by_topic: dict[FissureTopic, list[Fissure]],
    registry: EmojiRegistry,
) -> discord.Embed:
    """Persistent summary embed edited in place as the user's matches evolve.

    Sectioned by topic, each section a list of active matching fissures with
    a Discord native relative-timestamp so countdowns tick client-side
    between our edits. Empty state shows a hint rather than nothing — gives
    the user something to look at while they wait for the next rotation."""
    embed = discord.Embed(
        title="🔔  Your fissure subscriptions",
        color=discord.Color.blurple(),
    )
    has_any = any(matches_by_topic.get(t) for t in FissureTopic)
    if not has_any:
        embed.description = (
            "_No active fissures match your subscriptions right now._\n\n"
            "I'll edit this message as soon as something goes live. Use "
            "`/notifications` to fine-tune your filters."
        )
        return embed

    parts: list[str] = []
    for topic in FissureTopic:
        fissures = matches_by_topic.get(topic) or []
        if not fissures:
            continue
        parts.append(f"**{TOPIC_LABELS[topic]}**")
        # Sort by expiry so the soonest-rotating shows up first.
        for f in sorted(fissures, key=lambda x: x.expires_at):
            parts.append(_fissure_row(f, registry))
        parts.append("")  # blank line between topic sections
    embed.description = "\n".join(parts).rstrip()
    embed.set_footer(
        text="Entries auto-remove when expired • /notifications to filter"
    )
    return embed


def build_alert_text(new_fissures: list[Fissure]) -> str:
    """Short text-only ping for newly-available fissures. Kept terse so the
    DM history doesn't fill up; auto-deleted by the notifier when the
    fissure window expires."""
    if len(new_fissures) == 1:
        f = new_fissures[0]
        location = f"{f.node} ({f.planet})" if f.planet else f.node
        sp = "Steel Path " if f.is_steel_path else ""
        return (
            f"⚡ **{sp}{f.era.value} {f.mission_type.value}** at {location} "
            f"— expires <t:{int(f.expires_at.timestamp())}:R>"
        )
    return (
        f"⚡ **{len(new_fissures)} new fissures** match your subscriptions "
        f"— see your summary."
    )


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


# The previous per-fissure ``build_notification_embed`` is gone — the
# notifier now maintains a single persistent summary message per user
# (see ``build_user_summary_embed`` above) plus terse text alerts
# (``build_alert_text``), which together replace the per-fissure embed
# flood and survive bot restarts.
