"""Multi-vendor summary embed + Archon-shard resolution.

Covers the vendors-tab rework: the summary embed (Baro line + Teshin + Archon
Hunt) and the Archon → shard-colour mapping that feeds it.
"""

from datetime import datetime, timedelta, timezone

import pytest

from titania.domain.baro import BaroBoard, VoidTraderState
from titania.domain.vendors import (
    current_shiny_treasure_shard,
    current_teshin_reward,
    resolve_archon,
)
from titania.i18n.translator import Translator
from titania.presentation.vendor_embed import build_vendors_embed
from titania.services.emoji_registry import EmojiRegistry

UTC = timezone.utc
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


@pytest.fixture
def en() -> Translator:
    return Translator("en")


@pytest.fixture
def registry() -> EmojiRegistry:
    return EmojiRegistry()


def _absent_board() -> BaroBoard:
    state = VoidTraderState(
        character="Baro Ki'Teer",
        location="Larunda Relay (Mercury)",
        activation=NOW + timedelta(days=5),
        expiry=NOW + timedelta(days=7),
        inventory=(),
    )
    return BaroBoard(state=state, enriched_inventory=(), generated_at=NOW)


def _present_board() -> BaroBoard:
    class _BI:
        name, ducats, credits = "Prisma Grakata", 350, 100_000

    state = VoidTraderState(
        character="Baro Ki'Teer",
        location="Larunda Relay (Mercury)",
        activation=NOW - timedelta(hours=2),
        expiry=NOW + timedelta(days=1),
        inventory=(_BI(),),
    )
    return BaroBoard(state=state, enriched_inventory=(), generated_at=NOW)


# --- Archon resolution --------------------------------------------------------


@pytest.mark.parametrize(
    "boss,archon,color",
    [
        ("Archon Boreal", "Boreal", "blue"),
        ("Boreal", "Boreal", "blue"),
        ("Archon Amar", "Amar", "red"),
        ("Nira", "Nira", "amber"),
    ],
)
def test_resolve_archon_maps_boss_to_shard(boss, archon, color):
    shard = resolve_archon(boss)
    assert shard is not None
    assert shard.archon == archon
    assert shard.color == color


@pytest.mark.parametrize("boss", [None, "", "Some Other Boss"])
def test_resolve_archon_unknown_is_none(boss):
    assert resolve_archon(boss) is None


# --- weekly rotations (anchored to Mon 2026-08-10) ----------------------------

# Anytime in the anchor week (Mon 08-10 → before Mon 08-17).
_ANCHOR_WEEK = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def test_teshin_rotation_is_3_forma_in_anchor_week():
    assert current_teshin_reward(_ANCHOR_WEEK).name == "3× Forma"


def test_teshin_rotation_advances_weekly_and_wraps():
    # +1 week → Zaw Riven; the 8-item cycle wraps back to 3× Forma after 8 weeks.
    assert current_teshin_reward(_ANCHOR_WEEK + timedelta(weeks=1)).name == "Zaw Riven Mod"
    assert current_teshin_reward(_ANCHOR_WEEK + timedelta(weeks=8)).name == "3× Forma"


def test_shiny_treasures_rotation_blue_yellow_red():
    assert current_shiny_treasure_shard(_ANCHOR_WEEK).color == "blue"
    assert current_shiny_treasure_shard(_ANCHOR_WEEK + timedelta(weeks=1)).color == "amber"
    assert current_shiny_treasure_shard(_ANCHOR_WEEK + timedelta(weeks=2)).color == "red"
    assert current_shiny_treasure_shard(_ANCHOR_WEEK + timedelta(weeks=3)).color == "blue"


def test_rotation_respects_monday_reset_boundary():
    # Sunday 08-16 23:59 is still the anchor week; Monday 08-17 00:00 flips it.
    sun = datetime(2026, 8, 16, 23, 59, tzinfo=UTC)
    mon = datetime(2026, 8, 17, 0, 0, tzinfo=UTC)
    assert current_teshin_reward(sun).name == "3× Forma"
    assert current_teshin_reward(mon).name == "Zaw Riven Mod"


# --- summary embed ------------------------------------------------------------


def test_absent_baro_summary_is_single_line_with_location_and_countdown(en, registry):
    embed = build_vendors_embed(_absent_board(), en, registry)
    desc = embed.description or ""
    assert "\n" not in desc  # single line when Baro is away
    assert "Larunda Relay (Mercury)" in desc
    assert f"<t:{int((NOW + timedelta(days=5)).timestamp())}:R>" in desc


def test_present_baro_summary_shows_relay_and_inventory_link(en, registry):
    embed = build_vendors_embed(
        _present_board(), en, registry, inventory_mention="</vendors inventory:42>"
    )
    desc = embed.description or ""
    assert "Larunda Relay (Mercury)" in desc
    assert "</vendors inventory:42>" in desc
    # Departure countdown, not an inventory dump, lives on the summary.
    assert f"<t:{int((NOW + timedelta(days=1)).timestamp())}:R>" in desc


def test_present_baro_summary_falls_back_when_mention_missing(en, registry):
    embed = build_vendors_embed(_present_board(), en, registry, inventory_mention=None)
    assert "/vendors inventory" in (embed.description or "")


def _field_by_value(embed, needle):
    """Vendor sections live in field *values* (names are zero-width), so match
    on the value text."""
    return next(f for f in embed.fields if needle in (f.value or ""))


def test_summary_includes_teshin_and_archon_fields(en, registry):
    embed = build_vendors_embed(
        _absent_board(), en, registry, archon=resolve_archon("Boreal")
    )
    teshin = _field_by_value(embed, "Teshin")
    archon = _field_by_value(embed, "Archon Hunt")
    assert current_teshin_reward().name in (teshin.value or "")
    assert "Boreal" in (archon.value or "")
    assert "Azure" in (archon.value or "")


def test_summary_uses_real_icons_when_registry_has_them(en):
    class _StubRegistry(EmojiRegistry):
        def __init__(self):
            super().__init__()
            self._markup = {
                "forma": "<:forma:111>",
                "archon_shard_azure": "<:archon_shard_azure:222>",
            }

    embed = build_vendors_embed(
        _absent_board(), en, _StubRegistry(), archon=resolve_archon("Boreal")
    )
    assert "<:forma:111>" in (_field_by_value(embed, "Teshin").value or "")
    assert "<:archon_shard_azure:222>" in (_field_by_value(embed, "Archon Hunt").value or "")


def test_marker_precedes_vendor_name(en):
    class _StubRegistry(EmojiRegistry):
        def __init__(self):
            super().__init__()
            self._markup = {"steel_path": "<:steel:1>", "narmer": "<:narmer:2>"}

    embed = build_vendors_embed(
        _absent_board(), en, _StubRegistry(), archon=resolve_archon("Boreal")
    )
    teshin = _field_by_value(embed, "Teshin").value or ""
    archon = _field_by_value(embed, "Archon Hunt").value or ""
    assert teshin.index("<:steel:1>") < teshin.index("Teshin")
    assert archon.index("<:narmer:2>") < archon.index("Archon Hunt")


def test_summary_archon_field_unavailable_when_none(en, registry):
    embed = build_vendors_embed(_absent_board(), en, registry, archon=None)
    archon = _field_by_value(embed, "Archon Hunt")
    assert "Unavailable" in (archon.value or "")


def test_shiny_treasures_on_its_own_row_below_the_other_two(en, registry):
    # Independent vendor: renders even when the Archon Hunt is unavailable, and
    # sits on its own row (inline=False) beneath Teshin + Archon Hunt.
    embed = build_vendors_embed(_absent_board(), en, registry, archon=None)
    teshin, archon, shiny = embed.fields
    assert teshin.inline and archon.inline  # first row, side by side
    assert shiny.inline is False  # own row below
    assert "Shiny Treasures" in (shiny.value or "")
    assert current_shiny_treasure_shard().shard_name in (shiny.value or "")
