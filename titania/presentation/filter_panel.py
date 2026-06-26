import logging
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import discord

from titania.domain.mission_type import (
    DEFAULT_DOJOSHARE_NODES,
    FAST_MISSIONS,
    MissionType,
    parse_mission_type,
)
from titania.domain.subscription_filter import SubscriptionFilter
from titania.domain.topic import FissureTopic, TOPIC_LABELS

if TYPE_CHECKING:
    from titania.bot import TitaniaBot

log = logging.getLogger(__name__)

_PANEL_TIMEOUT_SECONDS = 600

# Planets shown in the planet selector. Capped at Discord's 25-option limit
# and ordered roughly by Star Chart progression.
_ALL_PLANETS: tuple[str, ...] = (
    "Mercury", "Venus", "Earth", "Lua", "Mars", "Phobos", "Deimos", "Ceres",
    "Jupiter", "Europa", "Saturn", "Uranus", "Neptune", "Pluto", "Sedna",
    "Eris", "Kuva Fortress", "Void", "Zariman",
)

# Dojoshare missions in practice — what the long-farm dojoshare nodes carry.
_DOJOSHARE_MISSIONS: tuple[MissionType, ...] = (
    MissionType.SURVIVAL,
    MissionType.DEFENSE,
)

# Stable ordering for the "fast" set so the dropdown order doesn't change
# between renders.
_FAST_MISSION_ORDER: tuple[MissionType, ...] = (
    MissionType.EXTERMINATE,
    MissionType.SABOTAGE,
    MissionType.CAPTURE,
    MissionType.RESCUE,
)

_TOPIC_SHORT: dict[FissureTopic, str] = {
    FissureTopic.NORMAL_FAST: "Normal",
    FissureTopic.SP_FAST: "SP",
    FissureTopic.DOJOSHARE: "Dojo",
    FissureTopic.SP_TUVUL_CASCADE: "Cascade",
}


@dataclass(frozen=True)
class _TopicConfig:
    """Per-topic shape of the filter UI.

    - ``missions``: dropdown options. Empty = no mission filter shown (the
      topic is already mission-specific or single-node).
    - ``planets``: same idea.
    - ``node_mode``: ``"select"`` shows a multi-select populated from the
      guild's dojoshare list; ``"modal"`` opens a text-input modal for
      free-form node names; ``"none"`` hides node controls entirely.
    """

    missions: tuple[MissionType, ...]
    planets: tuple[str, ...]
    node_mode: str  # "select" | "modal" | "none"


# Fast topics use the canonical FAST_MISSIONS set; we pull the ordered tuple
# from _FAST_MISSION_ORDER and filter against the set so adding/removing
# entries in mission_type.py automatically flows through here.
_FAST_OPTIONS: tuple[MissionType, ...] = tuple(
    m for m in _FAST_MISSION_ORDER if m in FAST_MISSIONS
)

_TOPIC_CONFIGS: dict[FissureTopic, _TopicConfig] = {
    FissureTopic.NORMAL_FAST: _TopicConfig(
        missions=_FAST_OPTIONS, planets=_ALL_PLANETS, node_mode="modal",
    ),
    FissureTopic.SP_FAST: _TopicConfig(
        missions=_FAST_OPTIONS, planets=_ALL_PLANETS, node_mode="modal",
    ),
    FissureTopic.DOJOSHARE: _TopicConfig(
        missions=_DOJOSHARE_MISSIONS, planets=_ALL_PLANETS, node_mode="select",
    ),
    FissureTopic.SP_TUVUL_CASCADE: _TopicConfig(
        missions=(), planets=(), node_mode="none",
    ),
}


def _format_set(values: frozenset[str]) -> str:
    return ", ".join(sorted(values)) if values else "_any_"


def _format_missions(values: frozenset[MissionType]) -> str:
    return ", ".join(sorted(v.value for v in values)) if values else "_any_"


class _NodesModal(discord.ui.Modal, title="Edit node allowlist"):
    """Free-text node editor for fast topics where the node universe is too
    large for a 25-option multi-select."""

    nodes_input = discord.ui.TextInput(
        label="Comma-separated node names (blank = any)",
        placeholder="e.g. Apollodorus, Cervantes, Sui",
        required=False,
        style=discord.TextStyle.short,
        max_length=400,
    )

    def __init__(self, panel: "FilterPanel", current: frozenset[str]) -> None:
        super().__init__()
        self._panel = panel
        self.nodes_input.default = ", ".join(sorted(current))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = self.nodes_input.value or ""
        nodes = frozenset(s.strip() for s in raw.split(",") if s.strip())
        self._panel.current_filter = replace(self._panel.current_filter, nodes=nodes)
        await self._panel._save_and_refresh(interaction)


class FilterPanel(discord.ui.View):
    """Ephemeral, point-and-click panel for per-user fissure filters.

    The relevant options per topic are pre-narrowed:

    - **Normal Fast / SP Fast**: mission dropdown only offers the canonical
      ``FAST_MISSIONS`` set (Exterminate, Sabotage, Capture, Rescue). Nodes
      use a modal because hundreds of fast-mission nodes exist.
    - **Dojoshare**: mission dropdown is Survival/Defense. Nodes are a
      multi-select drawn from the *guild's* dojoshare list, so it stays in
      sync with the operator's configuration.
    - **SP Tuvul Commons (Void Cascade)**: no filter controls — the topic
      already pins to a single node + mission.
    """

    def __init__(self, bot: "TitaniaBot", user_id: int) -> None:
        super().__init__(timeout=_PANEL_TIMEOUT_SECONDS)
        self._bot = bot
        self._user_id = user_id
        self.current_topic: FissureTopic | None = None
        self.current_filter: SubscriptionFilter = SubscriptionFilter()
        self._subscribed: set[str] = set()
        # Dojoshare node list shown in the multi-select. Sourced from the
        # bot-wide default since subscriptions aren't guild-scoped.
        self._dojoshare_nodes: tuple[str, ...] = tuple(
            sorted(DEFAULT_DOJOSHARE_NODES)
        )

    async def open(self, interaction: discord.Interaction) -> None:
        self._subscribed = set(
            await self._bot.subscriptions_repo.list_user_topics(self._user_id)
        )
        self._rebuild()
        await interaction.response.send_message(
            embed=self._build_embed(), view=self, ephemeral=True
        )

    # ---------- rendering ----------

    def _topic_style(self, topic: FissureTopic) -> discord.ButtonStyle:
        if topic is self.current_topic:
            return discord.ButtonStyle.primary  # blurple — currently editing
        if topic.value in self._subscribed:
            return discord.ButtonStyle.success  # green — subscribed
        return discord.ButtonStyle.secondary  # gray — not subscribed yet

    def _rebuild(self) -> None:
        self.clear_items()

        # Row 0 — topic selector
        for topic in FissureTopic:
            btn = discord.ui.Button(
                label=_TOPIC_SHORT[topic],
                style=self._topic_style(topic),
                row=0,
            )
            btn.callback = self._make_topic_callback(topic)
            self.add_item(btn)

        if self.current_topic is None:
            return

        cfg = _TOPIC_CONFIGS[self.current_topic]
        next_row = 1

        # Planet multi-select
        if cfg.planets:
            planet_select = discord.ui.Select(
                placeholder="Planets allowlist  (none selected = any)",
                min_values=0,
                max_values=len(cfg.planets),
                options=[
                    discord.SelectOption(
                        label=p,
                        value=p,
                        default=p in self.current_filter.planets,
                    )
                    for p in cfg.planets
                ],
                row=next_row,
            )
            planet_select.callback = self._on_planet_change
            self.add_item(planet_select)
            next_row += 1

        # Mission multi-select (per-topic option list)
        if cfg.missions:
            mission_select = discord.ui.Select(
                placeholder="Mission types allowlist  (none selected = any)",
                min_values=0,
                max_values=len(cfg.missions),
                options=[
                    discord.SelectOption(
                        label=mt.value,
                        value=mt.value,
                        default=mt in self.current_filter.mission_types,
                    )
                    for mt in cfg.missions
                ],
                row=next_row,
            )
            mission_select.callback = self._on_mission_change
            self.add_item(mission_select)
            next_row += 1

        # Nodes — multi-select for the small dojoshare list, modal for the
        # open-ended fast-mission node universe.
        if cfg.node_mode == "select" and self._dojoshare_nodes:
            node_select = discord.ui.Select(
                placeholder="Nodes allowlist  (none selected = any)",
                min_values=0,
                max_values=len(self._dojoshare_nodes),
                options=[
                    discord.SelectOption(
                        label=n,
                        value=n,
                        default=n in self.current_filter.nodes,
                    )
                    for n in self._dojoshare_nodes
                ],
                row=next_row,
            )
            node_select.callback = self._on_node_select_change
            self.add_item(node_select)
            next_row += 1
        elif cfg.node_mode == "modal":
            edit_nodes = discord.ui.Button(
                label="Edit nodes…",
                emoji="📝",
                style=discord.ButtonStyle.secondary,
                row=next_row,
            )
            edit_nodes.callback = self._on_edit_nodes
            self.add_item(edit_nodes)
            clear_nodes = discord.ui.Button(
                label="Clear nodes",
                style=discord.ButtonStyle.secondary,
                row=next_row,
                disabled=not self.current_filter.nodes,
            )
            clear_nodes.callback = self._on_clear_nodes
            self.add_item(clear_nodes)
            next_row += 1

        # Reset all filters — disabled when nothing is set so the danger
        # button doesn't look armed needlessly.
        reset = discord.ui.Button(
            label="Reset all filters",
            emoji="🧹",
            style=discord.ButtonStyle.danger,
            row=min(next_row, 4),
            disabled=self.current_filter.is_unrestricted,
        )
        reset.callback = self._on_reset_all
        self.add_item(reset)

    def _build_embed(self) -> discord.Embed:
        if self.current_topic is None:
            return discord.Embed(
                title="🔔  Notification filters",
                description=(
                    "Pick a topic above to start editing your filter.\n"
                    "Each topic keeps its own allowlist; empty = notify on all matches.\n\n"
                    "_Subscribe / unsubscribe via the reactions on the fissure tracker._"
                ),
                color=discord.Color.blurple(),
            )
        cfg = _TOPIC_CONFIGS[self.current_topic]
        embed = discord.Embed(
            title=f"🔔  Filter for {TOPIC_LABELS[self.current_topic]}",
            color=discord.Color.blurple(),
        )
        if not cfg.missions and not cfg.planets and cfg.node_mode == "none":
            embed.description = (
                "This topic is already specific (single node / single mission), "
                "so there's nothing extra to filter. The reaction on the "
                "tracker is enough."
            )
            return embed
        if self.current_topic.value not in self._subscribed:
            embed.description = (
                "_You're not subscribed to this topic yet — saving filters "
                "here will auto-subscribe you._"
            )
        if cfg.node_mode != "none":
            embed.add_field(
                name="📍  Nodes",
                value=_format_set(self.current_filter.nodes),
                inline=False,
            )
        if cfg.planets:
            embed.add_field(
                name="🪐  Planets",
                value=_format_set(self.current_filter.planets),
                inline=False,
            )
        if cfg.missions:
            embed.add_field(
                name="🎯  Mission types",
                value=_format_missions(self.current_filter.mission_types),
                inline=False,
            )
        return embed

    # ---------- callbacks ----------

    def _make_topic_callback(self, topic: FissureTopic):
        async def _cb(interaction: discord.Interaction) -> None:
            self.current_topic = topic
            existing = await self._bot.subscriptions_repo.get_filter(
                self._user_id, topic.value
            )
            self.current_filter = existing or SubscriptionFilter()
            self._rebuild()
            await interaction.response.edit_message(
                embed=self._build_embed(), view=self
            )
        return _cb

    async def _on_planet_change(self, interaction: discord.Interaction) -> None:
        new = frozenset(interaction.data.get("values", []))  # type: ignore[arg-type]
        self.current_filter = replace(self.current_filter, planets=new)
        await self._save_and_refresh(interaction)

    async def _on_mission_change(self, interaction: discord.Interaction) -> None:
        raw = interaction.data.get("values", [])  # type: ignore[arg-type]
        new = frozenset(parse_mission_type(v) for v in raw)
        self.current_filter = replace(self.current_filter, mission_types=new)
        await self._save_and_refresh(interaction)

    async def _on_node_select_change(self, interaction: discord.Interaction) -> None:
        new = frozenset(interaction.data.get("values", []))  # type: ignore[arg-type]
        self.current_filter = replace(self.current_filter, nodes=new)
        await self._save_and_refresh(interaction)

    async def _on_edit_nodes(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            _NodesModal(self, self.current_filter.nodes)
        )

    async def _on_clear_nodes(self, interaction: discord.Interaction) -> None:
        self.current_filter = self.current_filter.cleared_nodes()
        await self._save_and_refresh(interaction)

    async def _on_reset_all(self, interaction: discord.Interaction) -> None:
        self.current_filter = SubscriptionFilter()
        await self._save_and_refresh(interaction)

    async def _save_and_refresh(self, interaction: discord.Interaction) -> None:
        if self.current_topic is None:
            return
        try:
            await self._bot.subscriptions_repo.update_filter(
                self._user_id,
                self.current_topic.value,
                self.current_filter,
            )
        except Exception:
            log.exception(
                "filter update failed user=%s topic=%s",
                self._user_id, self.current_topic.value,
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Couldn't save that change. Try again.", ephemeral=True
                )
            return
        self._subscribed.add(self.current_topic.value)
        self._rebuild()
        # Modal submissions consume the response slot; everything else still
        # has it free for an inline edit_message.
        if interaction.response.is_done():
            await interaction.edit_original_response(
                embed=self._build_embed(), view=self
            )
        else:
            await interaction.response.edit_message(
                embed=self._build_embed(), view=self
            )
