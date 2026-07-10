"""Functional test for the Phobos node fallback path.

Warframestat's /solnodes doesn't ship Phobos entries — the settings and
filter panels have to seed the browser from ``PHOBOS_FALLBACK_NODES``
instead. Regression coverage for the bug report ("planets on Phobos are not
showing").
"""

from unittest.mock import MagicMock

import pytest

from titania.domain.node import PHOBOS_FALLBACK_NODES, NodeInfo


class _CatalogWithoutPhobos:
    """Stand-in for the /solnodes-derived node dict. Contains only Mars
    entries — Phobos is deliberately absent so the fallback path fires."""

    @staticmethod
    def build() -> dict[str, NodeInfo]:
        return {
            "Ara": NodeInfo(name="Ara", planet="Mars", mission_type_raw="Extermination"),
            "Tharsis": NodeInfo(name="Tharsis", planet="Mars", mission_type_raw="Mobile Defense"),
        }


def _settings_panel_with_phobos_browse():
    from titania.presentation.settings_panel import SettingsPanel

    panel = SettingsPanel.__new__(SettingsPanel)
    panel._node_details = _CatalogWithoutPhobos.build()
    panel._browse_planet = "Phobos"
    return panel


@pytest.fixture
def panel():
    return _settings_panel_with_phobos_browse()


def test_settings_panel_populates_phobos_from_fallback(panel):
    """When /solnodes has no Phobos entries and the user picks Phobos, the
    node select must show the static fallback list."""
    options = panel._nodes_for_browse_planet(current_set=frozenset())
    labels = {o.value for o in options}
    # Every fallback node reaches the dropdown (fallback list is <25).
    for node in PHOBOS_FALLBACK_NODES:
        assert node in labels


def test_settings_panel_only_uses_fallback_when_catalog_empty_for_planet(panel):
    """The Mars catalog entries must NOT bleed into a Phobos browse. Note
    that ``Tharsis`` is *also* in the Phobos fallback (it's canonically a
    Phobos node, only tagged Mars in /solnodes upstream), so we assert on
    an unambiguously-Mars-only name here."""
    options = panel._nodes_for_browse_planet(current_set=frozenset())
    labels = {o.value for o in options}
    assert "Ara" not in labels


def test_settings_panel_falls_back_when_browsing_a_planet_the_catalog_covers(panel):
    """Sanity: browsing Mars still uses the real catalog, not the Phobos
    fallback."""
    panel._browse_planet = "Mars"
    options = panel._nodes_for_browse_planet(current_set=frozenset())
    labels = {o.value for o in options}
    assert labels == {"Ara", "Tharsis"}


def test_settings_panel_shows_selected_phobos_nodes_first(panel):
    """User-pinned nodes should surface at the top of the select even inside
    the fallback path — otherwise a user with a specific pin might not see
    it in the 25-option cap."""
    already_pinned = frozenset({"Stickney"})
    options = panel._nodes_for_browse_planet(current_set=already_pinned)
    # The 'default=True' options are the ones already in current_set. The
    # first such option is the selected node.
    first_selected = next(o for o in options if o.default)
    assert first_selected.value == "Stickney"


def test_filter_panel_phobos_fallback_bypasses_mission_type_filter():
    """Fallback nodes have empty ``mission_type_raw``. The filter panel's
    catalog-scoped node dropdown treats empty types as 'always show' so
    users can still pin them regardless of their mission allowlist."""
    from titania.domain.mission_type import MissionType
    from titania.domain.subscription_filter import SubscriptionFilter
    from titania.domain.topic import FissureTopic
    from titania.presentation.filter_panel import FilterPanel, _TOPIC_CONFIGS

    panel = FilterPanel.__new__(FilterPanel)
    panel._node_details = _CatalogWithoutPhobos.build()
    panel._browse_planet = "Phobos"
    # Restrict to Capture only. Fallback nodes (no known mission type) must
    # still surface — they're pin candidates, not certainty statements.
    panel.current_filter = SubscriptionFilter(
        mission_types=frozenset({MissionType.CAPTURE})
    )
    cfg = _TOPIC_CONFIGS[FissureTopic.NORMAL_FAST]

    options = panel._nodes_for_browse_planet(cfg)
    labels = {o.value for o in options}
    # At least one Phobos fallback name comes through.
    assert any(n in labels for n in PHOBOS_FALLBACK_NODES)


def test_filter_panel_still_filters_by_mission_type_for_typed_catalog_entries():
    """Regression guard: the permissive gate above must only relax the
    filter for empty types — real catalog entries with a mismatched
    mission type still get excluded."""
    from titania.domain.mission_type import MissionType
    from titania.domain.subscription_filter import SubscriptionFilter
    from titania.domain.topic import FissureTopic
    from titania.presentation.filter_panel import FilterPanel, _TOPIC_CONFIGS

    panel = FilterPanel.__new__(FilterPanel)
    panel._node_details = {
        "MockCap": NodeInfo(name="MockCap", planet="Mars", mission_type_raw="Capture"),
        "MockExt": NodeInfo(name="MockExt", planet="Mars", mission_type_raw="Extermination"),
    }
    panel._browse_planet = "Mars"
    panel.current_filter = SubscriptionFilter(
        mission_types=frozenset({MissionType.CAPTURE})
    )
    cfg = _TOPIC_CONFIGS[FissureTopic.NORMAL_FAST]

    options = panel._nodes_for_browse_planet(cfg)
    labels = {o.value for o in options}
    assert "MockCap" in labels
    assert "MockExt" not in labels
