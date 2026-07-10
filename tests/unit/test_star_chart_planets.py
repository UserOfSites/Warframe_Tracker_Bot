"""Guard rails around the curated planet list.

The panel dropdowns are limited to 25 options, and only planets whose nodes
Titania can actually surface in fissures should be offered. The two
non-obvious cases:

* **Phobos** — kept in the list because its fissures are live and users
  need to pin/block them, but its nodes aren't in warframestat's
  ``/solnodes`` catalog. The panels merge in
  :data:`PHOBOS_FALLBACK_NODES` when the catalog draws a blank.
* **Kuva Fortress / Duviri** — dropped because they don't carry the
  relic content Titania surfaces (Requiem-only / Circuit-only).
"""

from titania.domain.node import PHOBOS_FALLBACK_NODES, STAR_CHART_PLANETS


def test_planet_list_fits_discord_select_option_cap():
    assert len(STAR_CHART_PLANETS) <= 25


def test_planet_list_has_no_duplicates():
    assert len(set(STAR_CHART_PLANETS)) == len(STAR_CHART_PLANETS)


def test_planet_list_includes_phobos():
    """Phobos has live fissures (see /pc/fissures — Stickney, Roche, …), so
    users need to reach it in the panels even though /solnodes doesn't ship
    Phobos nodes. The panels compensate via PHOBOS_FALLBACK_NODES."""
    assert "Phobos" in STAR_CHART_PLANETS


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


def test_phobos_fallback_covers_known_current_fissure_nodes():
    """The two Phobos nodes seen in live fissures during triage (Stickney,
    Roche) must appear in the fallback — those are our ground truth."""
    for known in ("Stickney", "Roche"):
        assert known in PHOBOS_FALLBACK_NODES, (
            f"{known} is a real Phobos fissure node and must be reachable "
            "via the fallback list"
        )


def test_phobos_fallback_fits_discord_select_option_cap():
    assert len(PHOBOS_FALLBACK_NODES) <= 25


def test_panels_share_the_same_planet_list():
    """Both panels used to hardcode their own copy. The bug this test guards
    against: the two lists drift apart and Phobos comes back in one panel
    but not the other."""
    from titania.presentation.filter_panel import _ALL_PLANETS as filter_planets
    from titania.presentation.settings_panel import _ALL_PLANETS as settings_planets

    assert filter_planets == STAR_CHART_PLANETS
    assert settings_planets == STAR_CHART_PLANETS
