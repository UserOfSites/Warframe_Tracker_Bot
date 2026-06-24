from dataclasses import replace
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from titania.domain.mission_type import (
    DEFAULT_DOJOSHARE_NODES,
    FAST_MISSIONS,
    MissionType,
    parse_mission_type,
)
from titania.services.guild_settings import GuildSettings  # noqa: F401

if TYPE_CHECKING:
    from titania.bot import TitaniaBot


_OWNER_PERMS = discord.Permissions(manage_guild=True)


def _format_list(values: frozenset[str]) -> str:
    if not values:
        return "_(empty)_"
    return ", ".join(sorted(values))


def _format_mission_types(values: frozenset[MissionType]) -> str:
    if not values:
        return "_(empty)_"
    return ", ".join(sorted(v.value for v in values))


async def _require_guild(interaction: discord.Interaction) -> int | None:
    """Settings only make sense inside a guild. Return guild_id or send an
    error and return None."""
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "Settings can only be configured in a server, not in DMs.",
            ephemeral=True,
        )
        return None
    return interaction.guild_id


def _bot(interaction: discord.Interaction) -> "TitaniaBot":
    return interaction.client  # type: ignore[return-value]


class Settings(
    commands.GroupCog,
    name="settings",
    description="Per-guild bot configuration (Manage Guild required).",
):
    fissures = app_commands.Group(
        name="fissures",
        description="Fissure filter settings.",
        default_permissions=_OWNER_PERMS,
    )

    # --- /settings fissures types --------------------------------------------

    @fissures.command(
        name="types",
        description="Manage which mission types appear in Normal + Steel Path sections.",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.choices(
        action=[
            app_commands.Choice(name="show", value="show"),
            app_commands.Choice(name="add", value="add"),
            app_commands.Choice(name="remove", value="remove"),
            app_commands.Choice(name="reset", value="reset"),
        ]
    )
    async def fissures_types(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        mission_type: str | None = None,
    ) -> None:
        guild_id = await _require_guild(interaction)
        if guild_id is None:
            return
        bot = _bot(interaction)
        current = await bot.settings_repo.get(guild_id)

        if action.value == "show":
            await interaction.response.send_message(
                f"Allowed mission types: {_format_mission_types(current.allowed_mission_types)}",
                ephemeral=True,
            )
            return

        if action.value == "reset":
            new = replace(current, allowed_mission_types=frozenset(FAST_MISSIONS))
            await bot.settings_repo.save(guild_id, new)
            await interaction.response.send_message(
                f"Reset to defaults: {_format_mission_types(new.allowed_mission_types)}",
                ephemeral=True,
            )
            return

        if mission_type is None:
            await interaction.response.send_message(
                "`mission_type` is required for add/remove.", ephemeral=True
            )
            return

        mt = parse_mission_type(mission_type)
        if mt is MissionType.OTHER:
            await interaction.response.send_message(
                f"Unknown mission type: `{mission_type}`.", ephemeral=True
            )
            return

        if action.value == "add":
            new_types = current.allowed_mission_types | {mt}
        else:  # remove
            new_types = current.allowed_mission_types - {mt}

        new = replace(current, allowed_mission_types=new_types)
        await bot.settings_repo.save(guild_id, new)
        await interaction.response.send_message(
            f"Updated. Allowed mission types: {_format_mission_types(new.allowed_mission_types)}",
            ephemeral=True,
        )

    @fissures_types.autocomplete("mission_type")
    async def _mission_type_autocomplete(
        self, _interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        needle = current.strip().lower()
        return [
            app_commands.Choice(name=mt.value, value=mt.value)
            for mt in MissionType
            if mt is not MissionType.OTHER and needle in mt.value.lower()
        ][:25]

    # --- /settings fissures blocked-nodes ------------------------------------

    @fissures.command(
        name="blocked-nodes",
        description="Hide specific nodes from Normal + Steel Path (doesn't affect Dojoshare).",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.choices(
        action=[
            app_commands.Choice(name="show", value="show"),
            app_commands.Choice(name="block", value="block"),
            app_commands.Choice(name="unblock", value="unblock"),
            app_commands.Choice(name="clear", value="clear"),
        ]
    )
    async def fissures_blocked_nodes(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        node: str | None = None,
    ) -> None:
        guild_id = await _require_guild(interaction)
        if guild_id is None:
            return
        bot = _bot(interaction)
        current = await bot.settings_repo.get(guild_id)

        if action.value == "show":
            await interaction.response.send_message(
                f"Blocked nodes: {_format_list(current.blocked_nodes)}", ephemeral=True
            )
            return

        if action.value == "clear":
            new = replace(current, blocked_nodes=frozenset())
            await bot.settings_repo.save(guild_id, new)
            await interaction.response.send_message(
                "Blocked-nodes list cleared.", ephemeral=True
            )
            return

        if node is None:
            await interaction.response.send_message(
                "`node` is required for block/unblock.", ephemeral=True
            )
            return

        catalog = await bot.data_source.fetch_node_catalog()
        canonical = _canonicalize_node(node, catalog)
        if canonical is None:
            await interaction.response.send_message(
                f"Unknown node: `{node}`.", ephemeral=True
            )
            return

        if action.value == "block":
            new_blocked = current.blocked_nodes | {canonical}
        else:  # unblock
            new_blocked = frozenset(
                n for n in current.blocked_nodes if n.lower() != canonical.lower()
            )

        new = replace(current, blocked_nodes=new_blocked)
        await bot.settings_repo.save(guild_id, new)
        await interaction.response.send_message(
            f"Updated. Blocked nodes: {_format_list(new.blocked_nodes)}", ephemeral=True
        )

    @fissures_blocked_nodes.autocomplete("node")
    async def _blocked_node_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await _autocomplete_for(
            interaction, current, "unblock", _attr_blocked_nodes
        )

    # --- /settings fissures pinned-nodes -------------------------------------

    @fissures.command(
        name="pinned-nodes",
        description="Always-show specific nodes in Normal + Steel Path, bypassing the mission-type filter.",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.choices(
        action=[
            app_commands.Choice(name="show", value="show"),
            app_commands.Choice(name="pin", value="pin"),
            app_commands.Choice(name="unpin", value="unpin"),
            app_commands.Choice(name="clear", value="clear"),
        ]
    )
    async def fissures_pinned_nodes(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        node: str | None = None,
    ) -> None:
        guild_id = await _require_guild(interaction)
        if guild_id is None:
            return
        bot = _bot(interaction)
        current = await bot.settings_repo.get(guild_id)

        if action.value == "show":
            await interaction.response.send_message(
                f"Pinned nodes: {_format_list(current.pinned_nodes)}", ephemeral=True
            )
            return

        if action.value == "clear":
            new = replace(current, pinned_nodes=frozenset())
            await bot.settings_repo.save(guild_id, new)
            await interaction.response.send_message(
                "Pinned-nodes list cleared.", ephemeral=True
            )
            return

        if node is None:
            await interaction.response.send_message(
                "`node` is required for pin/unpin.", ephemeral=True
            )
            return

        catalog = await bot.data_source.fetch_node_catalog()
        canonical = _canonicalize_node(node, catalog)
        if canonical is None:
            await interaction.response.send_message(
                f"Unknown node: `{node}`.", ephemeral=True
            )
            return

        if action.value == "pin":
            new_pinned = current.pinned_nodes | {canonical}
        else:  # unpin
            new_pinned = frozenset(
                n for n in current.pinned_nodes if n.lower() != canonical.lower()
            )

        new = replace(current, pinned_nodes=new_pinned)
        await bot.settings_repo.save(guild_id, new)
        await interaction.response.send_message(
            f"Updated. Pinned nodes: {_format_list(new.pinned_nodes)}", ephemeral=True
        )

    @fissures_pinned_nodes.autocomplete("node")
    async def _pinned_node_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await _autocomplete_for(
            interaction, current, "unpin", _attr_pinned_nodes
        )

    # --- /settings dojoshare -------------------------------------------------

    @app_commands.command(
        name="dojoshare",
        description="Manage the dojoshare node list (Steel-Path-only long farms).",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.choices(
        action=[
            app_commands.Choice(name="show", value="show"),
            app_commands.Choice(name="add", value="add"),
            app_commands.Choice(name="remove", value="remove"),
            app_commands.Choice(name="reset", value="reset"),
        ]
    )
    async def dojoshare(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        node: str | None = None,
    ) -> None:
        guild_id = await _require_guild(interaction)
        if guild_id is None:
            return
        bot = _bot(interaction)
        current = await bot.settings_repo.get(guild_id)

        if action.value == "show":
            await interaction.response.send_message(
                f"Dojoshare nodes: {_format_list(current.dojoshare_nodes)}",
                ephemeral=True,
            )
            return

        if action.value == "reset":
            new = replace(current, dojoshare_nodes=frozenset(DEFAULT_DOJOSHARE_NODES))
            await bot.settings_repo.save(guild_id, new)
            await interaction.response.send_message(
                f"Reset to defaults: {_format_list(new.dojoshare_nodes)}",
                ephemeral=True,
            )
            return

        if node is None:
            await interaction.response.send_message(
                "`node` is required for add/remove.", ephemeral=True
            )
            return

        catalog = await bot.data_source.fetch_node_catalog()
        canonical = _canonicalize_node(node, catalog)
        if canonical is None:
            await interaction.response.send_message(
                f"Unknown node: `{node}`.", ephemeral=True
            )
            return

        if action.value == "add":
            new_dojo = current.dojoshare_nodes | {canonical}
        else:
            new_dojo = frozenset(
                n for n in current.dojoshare_nodes if n.lower() != canonical.lower()
            )

        new = replace(current, dojoshare_nodes=new_dojo)
        await bot.settings_repo.save(guild_id, new)
        await interaction.response.send_message(
            f"Updated. Dojoshare nodes: {_format_list(new.dojoshare_nodes)}",
            ephemeral=True,
        )

    @dojoshare.autocomplete("node")
    async def _dojoshare_node_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await _autocomplete_for(
            interaction, current, "remove", _attr_dojoshare_nodes
        )

    # --- /settings language --------------------------------------------------

    @app_commands.command(
        name="language",
        description="Set the guild's UI language.",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.choices(
        lang=[
            app_commands.Choice(name="English", value="en"),
            app_commands.Choice(name="Italiano", value="it"),
        ]
    )
    async def language(
        self,
        interaction: discord.Interaction,
        lang: app_commands.Choice[str],
    ) -> None:
        guild_id = await _require_guild(interaction)
        if guild_id is None:
            return
        bot = _bot(interaction)
        current = await bot.settings_repo.get(guild_id)
        new = replace(current, locale=lang.value)
        await bot.settings_repo.save(guild_id, new)
        await interaction.response.send_message(
            f"Language set to **{lang.name}**.", ephemeral=True
        )


def _canonicalize_node(typed: str, catalog: frozenset[str]) -> str | None:
    """Map a user-typed node to the catalog's casing. Returns None if unknown."""
    needle = typed.strip().lower()
    for n in catalog:
        if n.lower() == needle:
            return n
    return None


def _node_autocomplete(
    current: str, catalog: frozenset[str]
) -> list[app_commands.Choice[str]]:
    needle = current.strip().lower()
    matches = sorted(n for n in catalog if needle in n.lower())
    return [app_commands.Choice(name=n, value=n) for n in matches[:25]]


# Accessors that pluck the relevant per-guild list out of GuildSettings. Using
# an attrgetter-like pattern keeps the autocomplete branching in one place.
def _attr_blocked_nodes(s) -> frozenset[str]:
    return s.blocked_nodes


def _attr_pinned_nodes(s) -> frozenset[str]:
    return s.pinned_nodes


def _attr_dojoshare_nodes(s) -> frozenset[str]:
    return s.dojoshare_nodes


async def _autocomplete_for(
    interaction: discord.Interaction,
    current: str,
    removal_action: str,
    list_getter,
) -> list[app_commands.Choice[str]]:
    """For removal actions (unblock/unpin/remove), suggest from the guild's
    *current* list — small and relevant. For everything else (add/pin/block),
    suggest from the full Warframe node catalog."""
    bot = _bot(interaction)
    action_choice = getattr(interaction.namespace, "action", None)
    action_value = action_choice.value if hasattr(action_choice, "value") else action_choice
    if action_value == removal_action and interaction.guild_id is not None:
        settings = await bot.settings_repo.get(interaction.guild_id)
        return _node_autocomplete(current, list_getter(settings))
    catalog = await bot.data_source.fetch_node_catalog()
    return _node_autocomplete(current, catalog)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Settings(bot))  # type: ignore[arg-type]
