"""TennoCon-scale Baro tests for the compact-mode fallback.

Normal Baro visits ship ~15-20 items and use the two-column grid renderer.
TennoCon (annual) brings back most of Baro's historical inventory at once —
50-100+ items — which breaks Discord's 25-field / 6000-char embed limits
under the grid. These tests lock in the fallback behaviour: threshold
detection, category grouping, rarity sort, single-line format, and the
description-limit safety net.
"""

from datetime import date, datetime, timedelta, timezone

import discord
import pytest

from titania.domain.baro import (
    BaroBoard,
    EnrichedBaroItem,
    VoidTraderState,
)
from titania.i18n.translator import Translator
from titania.presentation.vendor_embed import (
    _CATEGORY_ORDER,
    _COMPACT_MODE_THRESHOLD,
    _categorize,
    _compact_line,
    _rarity_sort_key,
    _short_days,
    build_baro_inventory_embed,
)
from titania.services.emoji_registry import EmojiRegistry


UTC = timezone.utc
NOW = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)


def _item(
    name: str,
    *,
    ducats: int | None = 500,
    credits: int | None = 100_000,
    last_seen_days: int | None = 30,
    total: int = 3,
    item_type: str | None = "Weapon",
    wiki_known: bool = True,
) -> EnrichedBaroItem:
    last = (NOW.date() - timedelta(days=last_seen_days)) if last_seen_days is not None else None
    return EnrichedBaroItem(
        name=name,
        ducats=ducats,
        credits=credits,
        last_appearance=last,
        total_appearances=total,
        image_name=None,
        wiki_known=wiki_known,
        item_type=item_type,
    )


def _present_state(inventory: list[EnrichedBaroItem]) -> VoidTraderState:
    return VoidTraderState(
        character="Baro Ki'Teer",
        location="Orcus Relay (Pluto)",
        activation=NOW - timedelta(hours=2),
        expiry=NOW + timedelta(hours=44),
        inventory=tuple(
            # Only names are read from state.inventory for `is_present`; the
            # enriched list is what the renderer walks.
            type("BI", (), {"name": it.name, "ducats": it.ducats, "credits": it.credits})()
            for it in inventory
        ),
    )


def _board(items: list[EnrichedBaroItem]) -> BaroBoard:
    return BaroBoard(
        state=_present_state(items),
        enriched_inventory=tuple(items),
        generated_at=NOW,
    )


@pytest.fixture
def en() -> Translator:
    return Translator("en")


@pytest.fixture
def registry() -> EmojiRegistry:
    return EmojiRegistry()  # empty — items fall back to bullet prefixes


# --- categorization -----------------------------------------------------------


@pytest.mark.parametrize(
    "item_type,expected",
    [
        ("Weapon", "Weapons"),
        ("Primed Mod (Rifle)", "Mods"),
        ("Mod (Rifle)", "Mods"),
        ("Void Relic", "Relics"),
        ("Cosmetic (Armor)", "Cosmetics"),
        ("Cosmetic (Syandana)", "Cosmetics"),
        ("Skin", "Cosmetics"),
        ("Ship Decoration", "Cosmetics"),
        ("Glyph", "Cosmetics"),
        ("Emote", "Cosmetics"),
        ("Somachord", "Music"),
        (None, "Other"),
        ("Consumable", "Other"),
        ("", "Other"),
    ],
)
def test_categorize(item_type, expected):
    assert _categorize(_item("X", item_type=item_type)) == expected


def test_category_labels_are_ascii_only():
    """Category headers must not contain Unicode emoji — plain text keeps
    the aesthetic consistent with the rest of the bot and doesn't rely on
    per-platform emoji rendering."""
    for label in _CATEGORY_ORDER:
        assert label.isascii(), f"Non-ASCII in category label: {label!r}"


# --- sort order ---------------------------------------------------------------


def test_rarity_sort_puts_longest_gap_first():
    old = _item("OldGap", last_seen_days=800)
    mid = _item("MidGap", last_seen_days=180)
    fresh = _item("FreshGap", last_seen_days=14)
    first = _item("First", last_seen_days=None, total=1)
    unknown = _item("Unknown", last_seen_days=None, total=0, wiki_known=False)

    items = [fresh, unknown, mid, first, old]
    items.sort(key=lambda i: _rarity_sort_key(i, NOW))
    assert [i.name for i in items] == ["OldGap", "MidGap", "FreshGap", "First", "Unknown"]


# --- line format --------------------------------------------------------------


def test_short_days_formats():
    assert _short_days(3) == "3d"
    assert _short_days(59) == "59d"
    assert _short_days(90) == "3mo"
    assert _short_days(365) == "1y"
    assert _short_days(400) == "1y35d"


def test_compact_line_includes_ducats_and_last_seen():
    line = _compact_line(_item("Prisma Skana", ducats=350, last_seen_days=780), NOW)
    assert "**Prisma Skana**" in line
    assert "350d" in line
    assert "2y50d ago" in line
    assert line.startswith("• ")


def test_compact_line_marks_always_available_and_first():
    always = _compact_line(
        _item("Sands of Inaros BP", ducats=0, last_seen_days=None, total=0),
        NOW,
    )
    first = _compact_line(
        _item("Novel Cosmetic", ducats=200, last_seen_days=None, total=1),
        NOW,
    )
    assert "always" in always
    assert "first" in first


# --- routing / threshold ------------------------------------------------------


def test_below_threshold_uses_grid_layout(en, registry):
    items = [_item(f"Item {i}") for i in range(_COMPACT_MODE_THRESHOLD)]
    embed = build_baro_inventory_embed(_board(items), en, registry)
    # Grid mode renders items as inline fields — several of them.
    assert len(embed.fields) > 0
    # Compact mode injects the "N items on offer" header; grid mode does not.
    assert "on offer" not in (embed.description or "")


def test_above_threshold_switches_to_compact(en, registry):
    items = [_item(f"Item {i}") for i in range(_COMPACT_MODE_THRESHOLD + 1)]
    embed = build_baro_inventory_embed(_board(items), en, registry)
    # Compact mode: no inventory fields, everything lives in the description.
    assert not any(f.name and "Inventory" in f.name for f in embed.fields)
    assert "on offer" in (embed.description or "")


def test_compact_mode_groups_by_category_in_declared_order(en, registry):
    items = [
        _item("Sculpture", item_type="Ship Decoration"),
        _item("Prisma Grakata", item_type="Weapon"),
        _item("Naberus Somachord", item_type="Somachord"),
        _item("Primed Fury", item_type="Primed Mod (Melee)"),
        *[_item(f"Cosmetic {i}", item_type="Cosmetic (Armor)") for i in range(_COMPACT_MODE_THRESHOLD)],
    ]
    embed = build_baro_inventory_embed(_board(items), en, registry)
    desc = embed.description or ""
    # Header labels appear in the order defined by _CATEGORY_ORDER.
    positions = [(cat, desc.find(cat)) for cat in _CATEGORY_ORDER if cat in desc]
    ordered = sorted(positions, key=lambda p: p[1])
    assert [c for c, _ in positions] == [c for c, _ in ordered]


# --- description-limit safety net --------------------------------------------


def test_massive_inventory_stays_within_description_limit(en, registry):
    """Simulate a 200-item TennoCon dump. The compact renderer must produce
    a description ≤ Discord's 4096-char cap, even if it has to truncate."""
    items = [
        _item(
            f"Legendary Item {i:03d}",
            ducats=(i * 7) % 900 or 25,
            credits=(i * 1000) % 200_000,
            last_seen_days=i * 3 if i % 7 else None,
            item_type=[
                "Weapon", "Primed Mod (Rifle)", "Cosmetic (Armor)",
                "Void Relic", "Somachord", "Ship Decoration",
            ][i % 6],
        )
        for i in range(200)
    ]
    embed = build_baro_inventory_embed(_board(items), en, registry)
    assert len(embed.description or "") <= 4096
    # Truncation notice fires when we actually drop items.
    if "…and " in (embed.description or ""):
        assert "more item" in (embed.description or "")


def test_reasonable_tennocon_size_fits_without_truncation(en, registry):
    """A more realistic ~60-item TennoCon inventory should fit cleanly with
    no truncation."""
    items = [
        _item(
            f"TC {i:02d}",
            item_type=["Weapon", "Cosmetic (Armor)", "Void Relic", "Primed Mod"][i % 4],
            last_seen_days=(i * 20) % 900,
        )
        for i in range(60)
    ]
    embed = build_baro_inventory_embed(_board(items), en, registry)
    desc = embed.description or ""
    assert len(desc) <= 4096
    assert "…and" not in desc  # no truncation notice for this size
    # All 60 items should be represented — item labels are unique enough that
    # a substring check is enough.
    for i in range(60):
        assert f"TC {i:02d}" in desc, f"missing TC {i:02d} at 60-item scale"


# --- absent Baro still works -------------------------------------------------


def test_absent_baro_shows_countdown_regardless_of_threshold(en, registry):
    state = VoidTraderState(
        character="Baro Ki'Teer",
        location="Orcus Relay (Pluto)",
        activation=NOW + timedelta(days=3),
        expiry=NOW + timedelta(days=5),
        inventory=(),
    )
    board = BaroBoard(state=state, enriched_inventory=(), generated_at=NOW)
    embed = build_baro_inventory_embed(board, en, registry)
    assert "Arrives" in (embed.description or "")
    # No compact-mode header when there's nothing to render.
    assert "on offer" not in (embed.description or "")
