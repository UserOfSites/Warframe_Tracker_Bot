from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from titania.domain.mission_type import MissionType, parse_mission_type
from titania.domain.subscription_filter import SubscriptionFilter
from titania.domain.topic import FissureTopic, TOPIC_LABELS
from titania.presentation.filter_panel import FilterPanel

if TYPE_CHECKING:
    from titania.bot import TitaniaBot


# Hardcoded planet list — the in-game planet roster is stable and small. If
# Warframe ships a new planet, add it here. The autocomplete falls back to the
# raw user input so the user can still type one we haven't catalogued.
_KNOWN_PLANETS: tuple[str, ...] = (
    "Mercury",
    "Venus",
    "Earth",
    "Lua",
    "Mars",
    "Phobos",
    "Deimos",
    "Ceres",
    "Jupiter",
    "Europa",
    "Saturn",
    "Uranus",
    "Neptune",
    "Pluto",
    "Sedna",
    "Eris",
    "Kuva Fortress",
    "Void",
    "Zariman",
    "Albrecht's Laboratories",
)

# Mission types presented as Choice. Capped at 25 (Discord's hard limit). The
# selection mirrors what shows up on fissures in practice.
_MISSION_CHOICES: tuple[app_commands.Choice[str], ...] = tuple(
    app_commands.Choice(name=mt.value, value=mt.value)
    for mt in (
        MissionType.CAPTURE,
        MissionType.EXTERMINATE,
        MissionType.SABOTAGE,
        MissionType.SURVIVAL,
        MissionType.DEFENSE,
        MissionType.MOBILE_DEFENSE,
        MissionType.EXCAVATION,
        MissionType.INTERCEPTION,
        MissionType.DISRUPTION,
        MissionType.DEFECTION,
        MissionType.RESCUE,
        MissionType.SPY,
        MissionType.HIJACK,
        MissionType.ASSAULT,
        MissionType.ALCHEMY,
    )
)

_TOPIC_CHOICES: tuple[app_commands.Choice[str], ...] = tuple(
    app_commands.Choice(name=TOPIC_LABELS[t], value=t.value) for t in FissureTopic
)

_ACTION_CHOICES: tuple[app_commands.Choice[str], ...] = (
    app_commands.Choice(name="add", value="add"),
    app_commands.Choice(name="remove", value="remove"),
    app_commands.Choice(name="clear", value="clear"),
    app_commands.Choice(name="show", value="show"),
)


async def _require_guild(interaction: discord.Interaction) -> int | None:
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "Notifications are per-server — run this in a server channel.",
            ephemeral=True,
        )
        return None
    return interaction.guild_id


def _bot(interaction: discord.Interaction) -> "TitaniaBot":
    return interaction.client  # type: ignore[return-value]


def _topic_from_value(value: str) -> FissureTopic | None:
    try:
        return FissureTopic(value)
    except ValueError:
        return None


def _format_set(values: frozenset[str]) -> str:
    return ", ".join(sorted(values)) if values else "_any_"


def _format_missions(values: frozenset[MissionType]) -> str:
    return ", ".join(sorted(mt.value for mt in values)) if values else "_any_"


class Notifications(
    commands.GroupCog,
    name="notifications",
    description="Per-user filters for fissure DM notifications.",
):
    """Slash commands that let each user narrow what their topic subscriptions
    DM them about. Topic membership itself stays on the reaction buttons of
    the tracker; this cog only edits the per-(user, topic) allowlist filter."""

    nodes = app_commands.Group(name="nodes", description="Filter by node name.")
    planets = app_commands.Group(name="planets", description="Filter by planet.")
    missions = app_commands.Group(
        name="missions", description="Filter by mission type."
    )

    def __init__(self, bot: "TitaniaBot") -> None:
        self.bot = bot

    # ---------- /notifications panel ----------

    @app_commands.command(
        name="panel",
        description="Open the visual filter panel — click to manage subscriptions and filters.",
    )
    async def panel(self, interaction: discord.Interaction) -> None:
        guild_id = await _require_guild(interaction)
        if guild_id is None:
            return
        panel = FilterPanel(self.bot, guild_id, interaction.user.id)
        await panel.open(interaction)

    # ---------- /notifications show ----------

    @app_commands.command(
        name="show",
        description="Show your current fissure subscriptions and per-topic filters.",
    )
    async def show(self, interaction: discord.Interaction) -> None:
        guild_id = await _require_guild(interaction)
        if guild_id is None:
            return
        user_id = interaction.user.id
        topics_subscribed = set(
            await self.bot.subscriptions_repo.list_user_topics(guild_id, user_id)
        )

        lines: list[str] = ["**Your fissure notifications:**\n"]
        for topic in FissureTopic:
            label = TOPIC_LABELS[topic]
            if topic.value not in topics_subscribed:
                lines.append(f"⬜  **{label}** — _not subscribed_")
                continue
            sub_filter = await self.bot.subscriptions_repo.get_filter(
                guild_id, user_id, topic.value
            )
            assert sub_filter is not None
            lines.append(f"✅  **{label}**")
            lines.append(f"   Nodes: {_format_set(sub_filter.nodes)}")
            lines.append(f"   Planets: {_format_set(sub_filter.planets)}")
            lines.append(f"   Missions: {_format_missions(sub_filter.mission_types)}")
        lines.append(
            "\n_Subscribe/unsubscribe via the reactions on the tracked fissures embed._"
        )
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    # ---------- /notifications nodes <action> ----------

    @nodes.command(
        name="manage",
        description="Add/remove/clear/show node filter for a topic.",
    )
    @app_commands.describe(
        topic="Which subscription to filter.",
        action="What to do.",
        node="Node name (autocompleted). Required for add/remove.",
    )
    @app_commands.choices(topic=list(_TOPIC_CHOICES), action=list(_ACTION_CHOICES))
    async def nodes_manage(
        self,
        interaction: discord.Interaction,
        topic: app_commands.Choice[str],
        action: app_commands.Choice[str],
        node: str | None = None,
    ) -> None:
        await self._apply_set_filter(
            interaction,
            topic=topic,
            action=action,
            value=node,
            field_label="Nodes",
            get_current=lambda f: f.nodes,
            add=lambda f, v: f.with_node_added(v),
            remove=lambda f, v: f.with_node_removed(v),
            clear=lambda f: f.cleared_nodes(),
            value_required_msg="`node` is required for add/remove.",
            value_canonicalizer=self._canonicalize_node,
        )

    @nodes_manage.autocomplete("node")
    async def _nodes_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            catalog = await self.bot.data_source.fetch_node_catalog()
        except Exception:
            return []
        needle = current.strip().lower()
        matches = sorted(n for n in catalog if needle in n.lower())[:25]
        return [app_commands.Choice(name=n, value=n) for n in matches]

    # ---------- /notifications planets <action> ----------

    @planets.command(
        name="manage",
        description="Add/remove/clear/show planet filter for a topic.",
    )
    @app_commands.describe(
        topic="Which subscription to filter.",
        action="What to do.",
        planet="Planet name. Required for add/remove.",
    )
    @app_commands.choices(topic=list(_TOPIC_CHOICES), action=list(_ACTION_CHOICES))
    async def planets_manage(
        self,
        interaction: discord.Interaction,
        topic: app_commands.Choice[str],
        action: app_commands.Choice[str],
        planet: str | None = None,
    ) -> None:
        await self._apply_set_filter(
            interaction,
            topic=topic,
            action=action,
            value=planet,
            field_label="Planets",
            get_current=lambda f: f.planets,
            add=lambda f, v: f.with_planet_added(v),
            remove=lambda f, v: f.with_planet_removed(v),
            clear=lambda f: f.cleared_planets(),
            value_required_msg="`planet` is required for add/remove.",
            value_canonicalizer=lambda v: _canonicalize_planet(v),
        )

    @planets_manage.autocomplete("planet")
    async def _planets_autocomplete(
        self, _interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        needle = current.strip().lower()
        matches = [p for p in _KNOWN_PLANETS if needle in p.lower()][:25]
        return [app_commands.Choice(name=p, value=p) for p in matches]

    # ---------- /notifications missions <action> ----------

    @missions.command(
        name="manage",
        description="Add/remove/clear/show mission-type filter for a topic.",
    )
    @app_commands.describe(
        topic="Which subscription to filter.",
        action="What to do.",
        mission="Mission type. Required for add/remove.",
    )
    @app_commands.choices(
        topic=list(_TOPIC_CHOICES),
        action=list(_ACTION_CHOICES),
        mission=list(_MISSION_CHOICES),
    )
    async def missions_manage(
        self,
        interaction: discord.Interaction,
        topic: app_commands.Choice[str],
        action: app_commands.Choice[str],
        mission: app_commands.Choice[str] | None = None,
    ) -> None:
        mt = parse_mission_type(mission.value) if mission else None
        await self._apply_mission_filter(interaction, topic, action, mt)

    # ---------- shared filter mutation core ----------

    async def _apply_set_filter(
        self,
        interaction: discord.Interaction,
        *,
        topic: app_commands.Choice[str],
        action: app_commands.Choice[str],
        value: str | None,
        field_label: str,
        get_current,
        add,
        remove,
        clear,
        value_required_msg: str,
        value_canonicalizer,
    ) -> None:
        guild_id = await _require_guild(interaction)
        if guild_id is None:
            return
        t = _topic_from_value(topic.value)
        if t is None:
            await interaction.response.send_message(
                f"Unknown topic: {topic.value}", ephemeral=True
            )
            return
        user_id = interaction.user.id
        current_filter = (
            await self.bot.subscriptions_repo.get_filter(guild_id, user_id, topic.value)
            or SubscriptionFilter()
        )

        if action.value == "show":
            await interaction.response.send_message(
                f"**{TOPIC_LABELS[t]}** — {field_label}: "
                f"{_format_set(get_current(current_filter))}",
                ephemeral=True,
            )
            return

        if action.value == "clear":
            new_filter = clear(current_filter)
            await self.bot.subscriptions_repo.update_filter(
                guild_id, user_id, topic.value, new_filter
            )
            await interaction.response.send_message(
                f"Cleared **{field_label}** filter for **{TOPIC_LABELS[t]}**.",
                ephemeral=True,
            )
            return

        if value is None:
            await interaction.response.send_message(value_required_msg, ephemeral=True)
            return

        canonical = await value_canonicalizer(value) if _is_async(value_canonicalizer) else value_canonicalizer(value)
        if canonical is None:
            await interaction.response.send_message(
                f"Unknown {field_label.lower().rstrip('s')}: `{value}`.", ephemeral=True
            )
            return

        if action.value == "add":
            new_filter = add(current_filter, canonical)
        else:  # remove
            new_filter = remove(current_filter, canonical)
        await self.bot.subscriptions_repo.update_filter(
            guild_id, user_id, topic.value, new_filter
        )
        await interaction.response.send_message(
            f"Updated. **{TOPIC_LABELS[t]}** — {field_label}: "
            f"{_format_set(get_current(new_filter))}",
            ephemeral=True,
        )

    async def _apply_mission_filter(
        self,
        interaction: discord.Interaction,
        topic: app_commands.Choice[str],
        action: app_commands.Choice[str],
        mt: MissionType | None,
    ) -> None:
        guild_id = await _require_guild(interaction)
        if guild_id is None:
            return
        t = _topic_from_value(topic.value)
        if t is None:
            await interaction.response.send_message(
                f"Unknown topic: {topic.value}", ephemeral=True
            )
            return
        user_id = interaction.user.id
        current_filter = (
            await self.bot.subscriptions_repo.get_filter(guild_id, user_id, topic.value)
            or SubscriptionFilter()
        )

        if action.value == "show":
            await interaction.response.send_message(
                f"**{TOPIC_LABELS[t]}** — Missions: "
                f"{_format_missions(current_filter.mission_types)}",
                ephemeral=True,
            )
            return

        if action.value == "clear":
            new_filter = current_filter.cleared_missions()
            await self.bot.subscriptions_repo.update_filter(
                guild_id, user_id, topic.value, new_filter
            )
            await interaction.response.send_message(
                f"Cleared **Missions** filter for **{TOPIC_LABELS[t]}**.",
                ephemeral=True,
            )
            return

        if mt is None:
            await interaction.response.send_message(
                "`mission` is required for add/remove.", ephemeral=True
            )
            return

        if action.value == "add":
            new_filter = current_filter.with_mission_added(mt)
        else:
            new_filter = current_filter.with_mission_removed(mt)
        await self.bot.subscriptions_repo.update_filter(
            guild_id, user_id, topic.value, new_filter
        )
        await interaction.response.send_message(
            f"Updated. **{TOPIC_LABELS[t]}** — Missions: "
            f"{_format_missions(new_filter.mission_types)}",
            ephemeral=True,
        )

    # ---------- helpers ----------

    async def _canonicalize_node(self, value: str) -> str | None:
        """Best-effort canonical-case match against the live node catalog."""
        try:
            catalog = await self.bot.data_source.fetch_node_catalog()
        except Exception:
            return value.strip() or None
        v = value.strip().lower()
        for n in catalog:
            if n.lower() == v:
                return n
        return None


def _canonicalize_planet(value: str) -> str | None:
    v = value.strip().lower()
    for p in _KNOWN_PLANETS:
        if p.lower() == v:
            return p
    # Accept unknown planets too — the filter still works, just won't match if
    # the upstream uses a different spelling.
    return value.strip() or None


def _is_async(fn) -> bool:
    import inspect
    return inspect.iscoroutinefunction(fn)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Notifications(bot))  # type: ignore[arg-type]
