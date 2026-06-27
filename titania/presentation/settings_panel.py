import logging
from dataclasses import replace
from enum import StrEnum
from typing import TYPE_CHECKING

import discord

from titania.domain.mission_type import (
    DEFAULT_DOJOSHARE_NODES,
    FAST_MISSIONS,
    MissionType,
    parse_mission_type,
)
from titania.domain.node import NodeInfo
from titania.services.guild_settings import GuildSettings

if TYPE_CHECKING:
    from titania.bot import TitaniaBot

log = logging.getLogger(__name__)

_PANEL_TIMEOUT_SECONDS = 600


class _Category(StrEnum):
    MISSIONS = "missions"
    DOJOSHARE = "dojoshare"
    PINNED = "pinned"
    BLOCKED = "blocked"


_CATEGORY_LABELS: dict[_Category, str] = {
    _Category.MISSIONS: "Missions",
    _Category.DOJOSHARE: "Dojoshare",
    _Category.PINNED: "Pinned",
    _Category.BLOCKED: "Blocked",
}

_CATEGORY_DESCRIPTIONS: dict[_Category, str] = {
    _Category.MISSIONS: (
        "Which mission types appear on the tracker (server-wide). Default is "
        "the fast set: Exterminate, Sabotage, Capture, Rescue."
    ),
    _Category.DOJOSHARE: (
        "Steel-Path-only long-farm nodes — promoted to a separate tracker "
        "section and bypassing the mission filter."
    ),
    _Category.PINNED: (
        "Nodes that always appear on the tracker, regardless of the mission "
        "type filter. Use sparingly."
    ),
    _Category.BLOCKED: (
        "Nodes that never appear on the tracker, regardless of other rules."
    ),
}

_ALL_PLANETS: tuple[str, ...] = (
    "Mercury", "Venus", "Earth", "Lua", "Mars", "Phobos", "Deimos", "Ceres",
    "Jupiter", "Europa", "Saturn", "Uranus", "Neptune", "Pluto", "Sedna",
    "Eris", "Kuva Fortress", "Void", "Zariman",
)

# Mission types the operator may include. Railjack types (Skirmish, Volatile,
# Orphix) are filtered out at the data layer regardless, so we hide them. We
# also hide "Other" since it's a catch-all bucket not worth opting into.
_PANEL_MISSIONS: tuple[MissionType, ...] = (
    MissionType.EXTERMINATE,
    MissionType.SABOTAGE,
    MissionType.CAPTURE,
    MissionType.RESCUE,
    MissionType.SURVIVAL,
    MissionType.DEFENSE,
    MissionType.MOBILE_DEFENSE,
    MissionType.EXCAVATION,
    MissionType.INTERCEPTION,
    MissionType.DISRUPTION,
    MissionType.DEFECTION,
    MissionType.SPY,
    MissionType.HIJACK,
    MissionType.ASSAULT,
    MissionType.ALCHEMY,
)


def _format_set(values: frozenset[str]) -> str:
    return ", ".join(sorted(values)) if values else "_empty_"


def _format_missions(values: frozenset[MissionType]) -> str:
    return ", ".join(sorted(v.value for v in values)) if values else "_empty_"


class SettingsPanel(discord.ui.View):
    """Server-wide settings panel for guild owners.

    Categories:
      - **Missions**: multi-select of mission types (server-wide tracker filter)
      - **Dojoshare / Pinned / Blocked**: browse-planet single-select then a
        node multi-select of that planet's nodes (with mission type annotated
        in the label so operators can pick the right one).

    Mirrors the notifications FilterPanel layout for muscle-memory consistency.
    Reset on row 0 resets the *currently-selected* category to its default
    (Missions → FAST_MISSIONS; Dojoshare → DEFAULT_DOJOSHARE_NODES; Pinned &
    Blocked → empty).
    """

    def __init__(self, bot: "TitaniaBot", guild_id: int) -> None:
        super().__init__(timeout=_PANEL_TIMEOUT_SECONDS)
        self._bot = bot
        self._guild_id = guild_id
        self._settings: GuildSettings | None = None
        self.current_category: _Category | None = None
        # Panel-only state: which planet's nodes the user is browsing.
        self._browse_planet: str | None = None
        self._node_details: dict[str, NodeInfo] = {}

    async def open(self, interaction: discord.Interaction) -> None:
        self._settings = await self._bot.settings_repo.get(self._guild_id)
        try:
            self._node_details = await self._bot.data_source.fetch_node_details()
        except Exception:
            log.exception("could not load node catalog; node selectors disabled")
            self._node_details = {}
        self._rebuild()
        await interaction.response.send_message(
            embed=self._build_embed(), view=self, ephemeral=True
        )

    # ---------- rendering ----------

    def _category_style(self, cat: _Category) -> discord.ButtonStyle:
        if cat is self.current_category:
            return discord.ButtonStyle.primary
        return discord.ButtonStyle.secondary

    def _rebuild(self) -> None:
        self.clear_items()

        # Row 0 — category buttons + Reset
        for cat in _Category:
            btn = discord.ui.Button(
                label=_CATEGORY_LABELS[cat],
                style=self._category_style(cat),
                row=0,
            )
            btn.callback = self._make_category_callback(cat)
            self.add_item(btn)

        if self.current_category is not None:
            reset_btn = discord.ui.Button(
                label="Reset",
                emoji="🧹",
                style=discord.ButtonStyle.danger,
                row=0,
            )
            reset_btn.callback = self._on_reset_category
            self.add_item(reset_btn)

        if self.current_category is None or self._settings is None:
            return

        if self.current_category is _Category.MISSIONS:
            # Single mission multi-select.
            mission_select = discord.ui.Select(
                placeholder="Allowed mission types  (server-wide tracker filter)",
                min_values=0,
                max_values=len(_PANEL_MISSIONS),
                options=[
                    discord.SelectOption(
                        label=mt.value,
                        value=mt.value,
                        default=mt in self._settings.allowed_mission_types,
                    )
                    for mt in _PANEL_MISSIONS
                ],
                row=1,
            )
            mission_select.callback = self._on_missions_change
            self.add_item(mission_select)
            return

        # Node-list categories: browse-planet + node multi-select.
        browse = discord.ui.Select(
            placeholder="Browse planet for nodes  (pick one)",
            min_values=0,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=p,
                    value=p,
                    default=p == self._browse_planet,
                )
                for p in _ALL_PLANETS
            ],
            row=1,
        )
        browse.callback = self._on_browse_planet_change
        self.add_item(browse)

        if self._browse_planet:
            current_set = self._current_node_set()
            options = self._nodes_for_browse_planet(current_set)
            if options:
                node_select = discord.ui.Select(
                    placeholder=(
                        f"Nodes on {self._browse_planet}  "
                        f"({len(options)} shown)"
                    ),
                    min_values=0,
                    max_values=len(options),
                    options=options,
                    row=2,
                )
                node_select.callback = self._on_nodes_change
                self.add_item(node_select)

    def _current_node_set(self) -> frozenset[str]:
        assert self._settings is not None
        if self.current_category is _Category.DOJOSHARE:
            return self._settings.dojoshare_nodes
        if self.current_category is _Category.PINNED:
            return self._settings.pinned_nodes
        if self.current_category is _Category.BLOCKED:
            return self._settings.blocked_nodes
        return frozenset()

    def _nodes_for_browse_planet(
        self, current_set: frozenset[str]
    ) -> list[discord.SelectOption]:
        """Options for the per-planet node multi-select. All nodes on the
        browsed planet, with mission type in the label so operators can pick
        the right one. Already-selected nodes float to the top so they
        remain editable. Capped at 25."""
        if not self._node_details or not self._browse_planet:
            return []
        planet_lc = self._browse_planet.lower()
        on_planet = sorted(
            (info for info in self._node_details.values()
             if info.planet.lower() == planet_lc),
            key=lambda info: info.name,
        )
        selected = [info for info in on_planet if info.name in current_set]
        others = [info for info in on_planet if info.name not in current_set]
        merged = selected + others

        options: list[discord.SelectOption] = []
        for info in merged[:25]:
            mt = info.mission_type_raw or "?"
            label = f"{info.name} ({mt})"[:100]
            options.append(
                discord.SelectOption(
                    label=label,
                    value=info.name,
                    default=info.name in current_set,
                )
            )
        return options

    def _build_embed(self) -> discord.Embed:
        if self._settings is None:
            return discord.Embed(
                title="⚙️ Server settings",
                description="Loading…",
                color=discord.Color.blurple(),
            )
        embed = discord.Embed(
            title="⚙️ Server settings",
            color=discord.Color.blurple(),
        )
        if self.current_category is None:
            embed.description = (
                "Pick a category above to edit. Current values:"
            )
        else:
            embed.description = (
                f"_Editing **{_CATEGORY_LABELS[self.current_category]}**_ — "
                f"{_CATEGORY_DESCRIPTIONS[self.current_category]}"
            )
        embed.add_field(
            name="🎯  Allowed missions",
            value=_format_missions(self._settings.allowed_mission_types),
            inline=False,
        )
        embed.add_field(
            name="🏯  Dojoshare nodes",
            value=_format_set(self._settings.dojoshare_nodes),
            inline=False,
        )
        embed.add_field(
            name="📌  Pinned nodes",
            value=_format_set(self._settings.pinned_nodes),
            inline=False,
        )
        embed.add_field(
            name="🚫  Blocked nodes",
            value=_format_set(self._settings.blocked_nodes),
            inline=False,
        )
        return embed

    # ---------- callbacks ----------

    def _make_category_callback(self, cat: _Category):
        async def _cb(interaction: discord.Interaction) -> None:
            self.current_category = cat
            self._browse_planet = None  # fresh start when switching category
            self._rebuild()
            await interaction.response.edit_message(
                embed=self._build_embed(), view=self
            )
        return _cb

    async def _on_browse_planet_change(
        self, interaction: discord.Interaction
    ) -> None:
        values = interaction.data.get("values", [])  # type: ignore[arg-type]
        self._browse_planet = values[0] if values else None
        self._rebuild()
        await interaction.response.edit_message(
            embed=self._build_embed(), view=self
        )

    async def _on_missions_change(
        self, interaction: discord.Interaction
    ) -> None:
        assert self._settings is not None
        raw = interaction.data.get("values", [])  # type: ignore[arg-type]
        new_missions = frozenset(parse_mission_type(v) for v in raw)
        new_settings = replace(
            self._settings, allowed_mission_types=new_missions
        )
        await self._save(new_settings, interaction)

    async def _on_nodes_change(
        self, interaction: discord.Interaction
    ) -> None:
        assert self._settings is not None
        selected_for_planet = frozenset(
            interaction.data.get("values", [])  # type: ignore[arg-type]
        )
        # Preserve nodes from OTHER planets so switching the browse planet
        # doesn't wipe earlier selections.
        planet_lc = (self._browse_planet or "").lower()
        nodes_on_planet = {
            info.name for info in self._node_details.values()
            if info.planet.lower() == planet_lc
        }
        current = self._current_node_set()
        preserved = current - nodes_on_planet
        new_set = preserved | selected_for_planet

        new_settings: GuildSettings
        if self.current_category is _Category.DOJOSHARE:
            new_settings = replace(self._settings, dojoshare_nodes=new_set)
        elif self.current_category is _Category.PINNED:
            new_settings = replace(self._settings, pinned_nodes=new_set)
        elif self.current_category is _Category.BLOCKED:
            new_settings = replace(self._settings, blocked_nodes=new_set)
        else:
            return
        await self._save(new_settings, interaction)

    async def _on_reset_category(
        self, interaction: discord.Interaction
    ) -> None:
        assert self._settings is not None
        if self.current_category is _Category.MISSIONS:
            new = replace(self._settings, allowed_mission_types=FAST_MISSIONS)
        elif self.current_category is _Category.DOJOSHARE:
            new = replace(
                self._settings,
                dojoshare_nodes=frozenset(DEFAULT_DOJOSHARE_NODES),
            )
        elif self.current_category is _Category.PINNED:
            new = replace(self._settings, pinned_nodes=frozenset())
        elif self.current_category is _Category.BLOCKED:
            new = replace(self._settings, blocked_nodes=frozenset())
        else:
            return
        await self._save(new, interaction)

    async def _save(
        self,
        new_settings: GuildSettings,
        interaction: discord.Interaction,
    ) -> None:
        try:
            await self._bot.settings_repo.save(self._guild_id, new_settings)
        except Exception:
            log.exception("settings save failed guild=%s", self._guild_id)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Couldn't save that change. Try again.", ephemeral=True
                )
            return
        self._settings = new_settings
        self._rebuild()
        if interaction.response.is_done():
            await interaction.edit_original_response(
                embed=self._build_embed(), view=self
            )
        else:
            await interaction.response.edit_message(
                embed=self._build_embed(), view=self
            )
