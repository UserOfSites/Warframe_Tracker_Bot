"""Multi-vendor summary embed + Archon-shard resolution.

Covers the vendors-tab rework: the summary embed (Baro line + Teshin + Archon
Hunt) and the Archon → shard-colour mapping that feeds it.
"""

from datetime import datetime, timedelta, timezone

import pytest

from titania.domain.baro import BaroBoard, VoidTraderState
from titania.domain.vendors import TESHIN_WEEKLY_ITEM, resolve_archon
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


def test_summary_includes_teshin_and_archon_fields(en, registry):
    embed = build_vendors_embed(
        _absent_board(), en, registry, archon=resolve_archon("Boreal")
    )
    teshin = next(f for f in embed.fields if "Teshin" in (f.name or ""))
    archon = next(f for f in embed.fields if "Archon" in (f.name or ""))
    assert teshin.value == TESHIN_WEEKLY_ITEM
    assert "Boreal" in (archon.value or "")
    assert "Azure" in (archon.value or "")


def test_summary_archon_field_unavailable_when_none(en, registry):
    embed = build_vendors_embed(_absent_board(), en, registry, archon=None)
    archon = next(f for f in embed.fields if "Archon" in (f.name or ""))
    assert "Unavailable" in (archon.value or "")
