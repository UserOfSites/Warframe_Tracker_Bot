from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from titania.cogs.settings import Settings
from titania.domain.mission_type import (
    DEFAULT_DOJOSHARE_NODES,
    FAST_MISSIONS,
    MissionType,
)
from titania.domain.node import NodeInfo
from titania.presentation.settings_panel import SettingsPanel, _Category
from titania.services.guild_settings import GuildSettings


def test_settings_cog_registers_expected_commands():
    """All node/mission management lives behind /settings panel now. The cog
    keeps just `panel` and `language` at the top level."""
    cmd_names = {c.name for c in Settings.__cog_app_commands__}
    assert cmd_names == {"panel", "language"}


# --- SettingsPanel rendering --------------------------------------------------


def _settings(
    allowed_mission_types=None,
    blocked_nodes=None,
    pinned_nodes=None,
    dojoshare_nodes=None,
    locale="en",
) -> GuildSettings:
    return GuildSettings(
        allowed_mission_types=allowed_mission_types or FAST_MISSIONS,
        blocked_nodes=blocked_nodes or frozenset(),
        pinned_nodes=pinned_nodes or frozenset(),
        dojoshare_nodes=dojoshare_nodes or frozenset(),
        locale=locale,
    )


def _bot_stub(settings: GuildSettings, node_details: dict[str, NodeInfo] | None = None):
    bot = MagicMock()
    bot.settings_repo = MagicMock()
    bot.settings_repo.get = AsyncMock(return_value=settings)
    bot.settings_repo.save = AsyncMock()
    bot.data_source = MagicMock()
    bot.data_source.fetch_node_details = AsyncMock(return_value=node_details or {})
    return bot


@pytest.mark.asyncio
async def test_panel_topic_buttons_only_until_category_picked():
    panel = SettingsPanel(_bot_stub(_settings()), guild_id=1)
    panel._settings = _settings()
    panel._rebuild()
    # 4 category buttons; no Reset yet (no category selected).
    btns = [c for c in panel.children if isinstance(c, discord.ui.Button)]
    assert {b.label for b in btns} == {"Missions", "Dojoshare", "Pinned", "Blocked"}
    # No selects yet.
    selects = [c for c in panel.children if isinstance(c, discord.ui.Select)]
    assert selects == []


@pytest.mark.asyncio
async def test_panel_missions_category_shows_one_multi_select():
    panel = SettingsPanel(_bot_stub(_settings()), guild_id=1)
    panel._settings = _settings(allowed_mission_types=frozenset({MissionType.CAPTURE}))
    panel.current_category = _Category.MISSIONS
    panel._rebuild()
    selects = [c for c in panel.children if isinstance(c, discord.ui.Select)]
    assert len(selects) == 1
    sel = selects[0]
    # The default-marked option must match what's in the filter
    defaults = {opt.value for opt in sel.options if opt.default}
    assert defaults == {MissionType.CAPTURE.value}


@pytest.mark.asyncio
async def test_panel_nodes_category_browse_first_then_node_select():
    catalog = {
        "Apollodorus": NodeInfo("Apollodorus", "Mercury", "Capture"),
        "Caduceus": NodeInfo("Caduceus", "Mercury", "Exterminate"),
        "Hieracon": NodeInfo("Hieracon", "Pluto", "Excavation"),
    }
    panel = SettingsPanel(_bot_stub(_settings(), node_details=catalog), guild_id=1)
    panel._settings = _settings(pinned_nodes=frozenset({"Apollodorus"}))
    panel._node_details = catalog
    panel.current_category = _Category.PINNED

    # No browse planet yet -> only the browse planet selector is shown
    panel._rebuild()
    selects = [c for c in panel.children if isinstance(c, discord.ui.Select)]
    assert len(selects) == 1
    assert selects[0].placeholder.startswith("Browse planet")

    # Pick Mercury -> node multi-select appears with Mercury's two nodes
    panel._browse_planet = "Mercury"
    panel._rebuild()
    selects = [c for c in panel.children if isinstance(c, discord.ui.Select)]
    assert len(selects) == 2
    node_sel = selects[1]
    labels = [opt.label for opt in node_sel.options]
    assert any("Apollodorus" in lbl for lbl in labels)
    assert any("Caduceus" in lbl for lbl in labels)
    # Apollodorus was pinned -> shown as default
    defaults = {opt.value for opt in node_sel.options if opt.default}
    assert defaults == {"Apollodorus"}


@pytest.mark.asyncio
async def test_panel_preserves_other_planet_nodes_on_change():
    """Switching browse planet and editing should NOT wipe nodes added from
    earlier-browsed planets."""
    catalog = {
        "Apollodorus": NodeInfo("Apollodorus", "Mercury", "Capture"),
        "Hieracon": NodeInfo("Hieracon", "Pluto", "Excavation"),
        "Sui": NodeInfo("Sui", "Pluto", "Capture"),
    }
    settings = _settings(pinned_nodes=frozenset({"Apollodorus"}))  # Mercury
    bot = _bot_stub(settings, node_details=catalog)
    panel = SettingsPanel(bot, guild_id=1)
    panel._settings = settings
    panel._node_details = catalog
    panel.current_category = _Category.PINNED
    panel._browse_planet = "Pluto"
    panel._rebuild()

    # Simulate the user picking Sui from the Pluto node multi-select.
    interaction = MagicMock()
    interaction.data = {"values": ["Sui"]}
    interaction.response.is_done.return_value = False
    interaction.response.edit_message = AsyncMock()
    await panel._on_nodes_change(interaction)

    # Apollodorus (Mercury, untouched) must still be in pinned_nodes;
    # Sui (Pluto, just selected) must be added.
    bot.settings_repo.save.assert_awaited_once()
    saved_args = bot.settings_repo.save.await_args.args
    saved_settings = saved_args[1]
    assert saved_settings.pinned_nodes == frozenset({"Apollodorus", "Sui"})


@pytest.mark.asyncio
async def test_panel_reset_uses_per_category_default():
    """Reset on Dojoshare goes back to DEFAULT_DOJOSHARE_NODES; on Pinned/
    Blocked goes back to empty; on Missions goes back to FAST_MISSIONS."""
    settings = _settings(
        allowed_mission_types=frozenset({MissionType.SPY}),
        dojoshare_nodes=frozenset({"Helene"}),
        pinned_nodes=frozenset({"Mot"}),
    )
    bot = _bot_stub(settings)
    panel = SettingsPanel(bot, guild_id=1)
    panel._settings = settings

    async def call_reset(category):
        panel.current_category = category
        interaction = MagicMock()
        interaction.response.is_done.return_value = False
        interaction.response.edit_message = AsyncMock()
        await panel._on_reset_category(interaction)
        return bot.settings_repo.save.await_args.args[1]

    new = await call_reset(_Category.MISSIONS)
    assert new.allowed_mission_types == FAST_MISSIONS
    new = await call_reset(_Category.DOJOSHARE)
    assert new.dojoshare_nodes == frozenset(DEFAULT_DOJOSHARE_NODES)
    new = await call_reset(_Category.PINNED)
    assert new.pinned_nodes == frozenset()
    new = await call_reset(_Category.BLOCKED)
    assert new.blocked_nodes == frozenset()
