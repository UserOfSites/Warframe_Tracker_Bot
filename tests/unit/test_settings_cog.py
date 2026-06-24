from unittest.mock import AsyncMock, MagicMock

import pytest

from titania.cogs.settings import (
    Settings,
    _autocomplete_for,
    _attr_pinned_nodes,
    _canonicalize_node,
    _node_autocomplete,
)
from titania.domain.mission_type import FAST_MISSIONS
from titania.services.guild_settings import GuildSettings


def test_canonicalize_matches_case_insensitively():
    catalog = frozenset({"Hepit", "Ukko", "Mot"})
    assert _canonicalize_node("hepit", catalog) == "Hepit"
    assert _canonicalize_node("  HEPIT  ", catalog) == "Hepit"
    assert _canonicalize_node("ukko", catalog) == "Ukko"


def test_canonicalize_returns_none_for_unknown():
    catalog = frozenset({"Hepit"})
    assert _canonicalize_node("Nonexistent", catalog) is None
    assert _canonicalize_node("", catalog) is None


def test_autocomplete_filters_by_substring_case_insensitive():
    catalog = frozenset({"Hepit", "Helene", "Hydron", "Ukko"})
    matches = _node_autocomplete("he", catalog)
    assert {c.value for c in matches} == {"Helene", "Hepit"}


def test_autocomplete_returns_all_sorted_for_empty_query():
    catalog = frozenset({"Hepit", "Akkad", "Mot"})
    matches = _node_autocomplete("", catalog)
    assert [c.value for c in matches] == ["Akkad", "Hepit", "Mot"]


def test_autocomplete_capped_at_25_results():
    catalog = frozenset(f"Node{i:03d}" for i in range(50))
    matches = _node_autocomplete("", catalog)
    assert len(matches) == 25


def test_settings_cog_registers_expected_commands():
    # GroupCog with name="settings" exposes its commands under /settings.
    cmd_names = {c.name for c in Settings.__cog_app_commands__}
    # Top-level (under /settings): the dojoshare, language commands, and the
    # `fissures` subcommand group.
    assert "dojoshare" in cmd_names
    assert "language" in cmd_names
    assert "fissures" in cmd_names


def test_fissures_subgroup_has_types_blocked_and_pinned_nodes():
    sub_names = {c.name for c in Settings.fissures.commands}
    assert sub_names == {"types", "blocked-nodes", "pinned-nodes"}


# --- action-aware autocomplete -------------------------------------------------


def _interaction(action_value: str | None, guild_id: int = 99):
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.namespace = MagicMock()
    if action_value is None:
        interaction.namespace.action = None
    else:
        ac = MagicMock()
        ac.value = action_value
        interaction.namespace.action = ac
    return interaction


def _bot_stub(catalog: frozenset[str], settings: GuildSettings):
    bot = MagicMock()
    bot.data_source = MagicMock()
    bot.data_source.fetch_node_catalog = AsyncMock(return_value=catalog)
    bot.settings_repo = MagicMock()
    bot.settings_repo.get = AsyncMock(return_value=settings)
    return bot


@pytest.mark.asyncio
async def test_autocomplete_add_action_uses_full_catalog():
    catalog = frozenset({"Hepit", "Mot", "Draco", "Hieracon"})
    settings = GuildSettings(
        allowed_mission_types=FAST_MISSIONS,
        blocked_nodes=frozenset(),
        pinned_nodes=frozenset({"Mot"}),  # what user currently has
        dojoshare_nodes=frozenset(),
        locale="en",
    )
    bot = _bot_stub(catalog, settings)
    interaction = _interaction("pin")
    interaction.client = bot

    choices = await _autocomplete_for(interaction, "h", "unpin", _attr_pinned_nodes)
    values = {c.value for c in choices}
    # "pin" action → full catalog, filtered by "h" substring → Hepit and Hieracon
    assert values == {"Hepit", "Hieracon"}


@pytest.mark.asyncio
async def test_autocomplete_remove_action_uses_current_list():
    catalog = frozenset({"Hepit", "Mot", "Draco", "Hieracon"})
    settings = GuildSettings(
        allowed_mission_types=FAST_MISSIONS,
        blocked_nodes=frozenset(),
        pinned_nodes=frozenset({"Mot", "Hepit"}),
        dojoshare_nodes=frozenset(),
        locale="en",
    )
    bot = _bot_stub(catalog, settings)
    interaction = _interaction("unpin")
    interaction.client = bot

    choices = await _autocomplete_for(interaction, "", "unpin", _attr_pinned_nodes)
    values = {c.value for c in choices}
    # "unpin" action → only what's currently pinned, ignoring the catalog
    assert values == {"Mot", "Hepit"}
    bot.data_source.fetch_node_catalog.assert_not_awaited()


@pytest.mark.asyncio
async def test_autocomplete_remove_action_filters_current_list_by_query():
    catalog = frozenset({"Hepit", "Mot", "Draco", "Hieracon", "Helene"})
    settings = GuildSettings(
        allowed_mission_types=FAST_MISSIONS,
        blocked_nodes=frozenset(),
        pinned_nodes=frozenset({"Mot", "Hepit", "Helene"}),
        dojoshare_nodes=frozenset(),
        locale="en",
    )
    bot = _bot_stub(catalog, settings)
    interaction = _interaction("unpin")
    interaction.client = bot

    choices = await _autocomplete_for(interaction, "he", "unpin", _attr_pinned_nodes)
    values = {c.value for c in choices}
    # Only currently-pinned nodes matching "he"
    assert values == {"Hepit", "Helene"}


@pytest.mark.asyncio
async def test_autocomplete_unknown_action_defaults_to_full_catalog():
    catalog = frozenset({"Hepit"})
    settings = GuildSettings(
        allowed_mission_types=FAST_MISSIONS,
        blocked_nodes=frozenset(),
        pinned_nodes=frozenset(),
        dojoshare_nodes=frozenset(),
        locale="en",
    )
    bot = _bot_stub(catalog, settings)
    interaction = _interaction(None)
    interaction.client = bot

    choices = await _autocomplete_for(interaction, "", "unpin", _attr_pinned_nodes)
    assert [c.value for c in choices] == ["Hepit"]
