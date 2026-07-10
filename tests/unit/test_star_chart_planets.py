"""Guard rails around the curated planet list.

The panel dropdowns are limited to 25 options, and adding a planet that
warframestat doesn't ship nodes for (Phobos was the reason for this fix)
produces an empty node selector that reads as broken. Tests below lock the
curated list to a set of assertions that would catch the next regression.
"""

from titania.domain.node import STAR_CHART_PLANETS


def test_planet_list_fits_discord_select_option_cap():
    assert len(STAR_CHART_PLANETS) <= 25


def test_planet_list_has_no_duplicates():
    assert len(set(STAR_CHART_PLANETS)) == len(STAR_CHART_PLANETS)


def test_planet_list_excludes_phobos():
    """Phobos was folded into Mars in warframestat's /solnodes — including
    it produced an empty node dropdown when users picked it in the panel."""
    assert "Phobos" not in STAR_CHART_PLANETS


def test_planet_list_excludes_kuva_fortress():
    """Kuva Fortress fissures are Requiem-only, and Requiem is filtered
    globally as not relic-relevant. No non-Requiem content there for us."""
    assert "Kuva Fortress" not in STAR_CHART_PLANETS


def test_planet_list_excludes_duviri():
    """Duviri has no regular fissure rotation; only the Circuit content,
    which Titania doesn't track."""
    assert "Duviri" not in STAR_CHART_PLANETS


def test_planet_list_includes_core_fissure_planets():
    for planet in (
        "Mercury", "Venus", "Earth", "Lua", "Mars", "Deimos", "Ceres",
        "Jupiter", "Europa", "Saturn", "Uranus", "Neptune", "Pluto", "Sedna",
        "Eris", "Void", "Zariman",
    ):
        assert planet in STAR_CHART_PLANETS, f"missing core planet: {planet}"


def test_panels_share_the_same_planet_list():
    """Both panels used to hardcode their own copy. The bug this test guards
    against: the two lists drift apart and Phobos comes back in one panel
    but not the other."""
    from titania.presentation.filter_panel import _ALL_PLANETS as filter_planets
    from titania.presentation.settings_panel import _ALL_PLANETS as settings_planets

    assert filter_planets == STAR_CHART_PLANETS
    assert settings_planets == STAR_CHART_PLANETS
