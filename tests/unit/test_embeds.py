from datetime import datetime, timedelta, timezone

import pytest

from titania.domain.era import Era
from titania.domain.fissure import Fissure, FissureBoard, NextReset
from titania.domain.mission_type import MissionType
from titania.i18n.translator import Translator
from titania.presentation.embeds import build_fissure_embed
from titania.services.emoji_registry import EmojiRegistry


class _StubRegistry(EmojiRegistry):
    """EmojiRegistry pre-populated with deterministic markup, no upload."""

    def __init__(self):
        super().__init__()
        self._markup = {
            "lith_relic": "<:lith_relic:1>",
            "meso_relic": "<:meso_relic:2>",
            "neo_relic": "<:neo_relic:3>",
            "axi_relic": "<:axi_relic:4>",
            "omnia_relic": "<:omnia_relic:5>",
            "steel_path": "<:steel_path:6>",
        }


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def registry() -> _StubRegistry:
    return _StubRegistry()


@pytest.fixture
def en() -> Translator:
    return Translator("en")


def _fissure(
    era: Era,
    mission_type: MissionType,
    node: str,
    planet: str,
    expires_at: datetime,
    is_steel_path: bool = False,
) -> Fissure:
    return Fissure(
        era=era,
        mission_type=mission_type,
        node=node,
        planet=planet,
        expires_at=expires_at,
        is_steel_path=is_steel_path,
        is_hard=False,
        tier=1,
    )


def _board(now: datetime) -> FissureBoard:
    return FissureBoard(
        normal=[
            _fissure(Era.LITH, MissionType.CAPTURE, "Hepit", "Void", now + timedelta(minutes=22)),
        ],
        steel_path=[
            _fissure(Era.NEO, MissionType.EXTERMINATE, "Teshub", "Void",
                     now + timedelta(hours=1, minutes=14), is_steel_path=True),
        ],
        dojoshare=[
            _fissure(Era.OMNIA, MissionType.SURVIVAL, "Yuvarium", "Lua",
                     now + timedelta(seconds=-1), is_steel_path=True),
        ],
        next_resets=[
            NextReset(era=Era.LITH, is_steel_path=False, expires_at=now + timedelta(minutes=36)),
            NextReset(era=Era.LITH, is_steel_path=True, expires_at=now + timedelta(minutes=8)),
        ],
        generated_at=now,
    )


def test_embed_uses_era_emoji_in_each_row(now, en, registry):
    embed = build_fissure_embed(_board(now), en, registry)
    desc = embed.description or ""
    assert "<:lith_relic:1>" in desc
    assert "<:neo_relic:3>" in desc
    assert "<:omnia_relic:5>" in desc


def test_steel_path_rows_prefix_with_steel_path_emoji(now, en, registry):
    embed = build_fissure_embed(_board(now), en, registry)
    desc = embed.description or ""
    # Both the SP row and the dojoshare row are Steel-Path → both get the marker.
    assert desc.count("<:steel_path:6>") == 2


def test_normal_rows_have_no_steel_path_emoji(now, en, registry):
    board = FissureBoard(
        normal=[_fissure(Era.LITH, MissionType.CAPTURE, "Hepit", "Void",
                          now + timedelta(minutes=10))],
        steel_path=[],
        dojoshare=[],
        next_resets=[],
        generated_at=now,
    )
    embed = build_fissure_embed(board, en, registry)
    assert "<:steel_path:6>" not in (embed.description or "")


def test_mission_uses_dash_separator_between_type_and_node(now, en, registry):
    embed = build_fissure_embed(_board(now), en, registry)
    desc = embed.description or ""
    assert "Capture — Hepit (Void)" in desc
    assert "Exterminate — Teshub (Void)" in desc


def test_time_is_rendered_as_discord_native_relative_timestamp(now, en, registry):
    """The countdown column uses Discord's native ``<t:UNIX:R>`` token. This
    renders legibly on every client (the previous inline-code form looked
    white-on-white on the mobile app) AND updates client-side, freeing the
    refresher from per-tick message edits just to tick the clock."""
    embed = build_fissure_embed(_board(now), en, registry)
    desc = embed.description or ""
    # Three fissures expire at known absolute timestamps; the embed should
    # carry each one verbatim as a Discord relative-time token.
    expected_unix = [
        int((now + timedelta(minutes=22)).timestamp()),
        int((now + timedelta(hours=1, minutes=14)).timestamp()),
        int((now + timedelta(seconds=-1)).timestamp()),
    ]
    for ts in expected_unix:
        assert f"<t:{ts}:R>" in desc


def test_next_resets_split_into_two_inline_fields(now, en, registry):
    embed = build_fissure_embed(_board(now), en, registry)
    # Three top-section fields are gone; Next Resets is two inline fields.
    inline_fields = [f for f in embed.fields if f.inline]
    assert len(inline_fields) == 2
    normal_field = next(f for f in inline_fields if "Normal" in (f.name or ""))
    sp_field = next(f for f in inline_fields if "Steel Path" in (f.name or ""))
    assert "<:lith_relic:1>" in (normal_field.value or "")
    assert "<:lith_relic:1>" in (sp_field.value or "")


def test_ayatan_line_omitted_when_slot_not_provided(now, en, registry):
    """Backwards-compat: build_fissure_embed without ayatan_slot must render
    exactly as before — no extra field, no stray text."""
    embed = build_fissure_embed(_board(now), en, registry)
    for field in embed.fields:
        assert "Ayatan" not in (field.name or "")


def test_ayatan_line_added_when_slot_provided(now, en, registry):
    from datetime import timedelta
    from titania.domain.ayatan import AYATAN_SCULPTURES, AyatanSlot

    slot = AyatanSlot(
        current=AYATAN_SCULPTURES["Orta"],
        next=AYATAN_SCULPTURES["Valana"],
        changes_at=now + timedelta(minutes=42),
    )
    embed = build_fissure_embed(_board(now), en, registry, ayatan_slot=slot)
    ayatan_field = next(
        (f for f in embed.fields if "Ayatan" in (f.name or "")), None
    )
    assert ayatan_field is not None, "Ayatan field must be present"
    assert "Orta" in (ayatan_field.value or "")
    assert "Valana" in (ayatan_field.value or "")
    assert "2700" in (ayatan_field.value or "")  # Orta's full endo
    # Discord native timestamp for the changeover
    expected_ts = int((now + timedelta(minutes=42)).timestamp())
    assert f"<t:{expected_ts}:R>" in (ayatan_field.value or "")


def test_ayatan_field_lives_at_the_bottom_of_the_embed(now, en, registry):
    from datetime import timedelta
    from titania.domain.ayatan import AYATAN_SCULPTURES, AyatanSlot

    slot = AyatanSlot(
        current=AYATAN_SCULPTURES["Vaya"],
        next=AYATAN_SCULPTURES["Sah"],
        changes_at=now + timedelta(minutes=10),
    )
    embed = build_fissure_embed(_board(now), en, registry, ayatan_slot=slot)
    # Field order after Next Resets (Normal, Steel Path) → Ayatan is last.
    assert embed.fields[-1].name and "Ayatan" in embed.fields[-1].name


def test_registry_missing_emoji_falls_back_to_era_text(now, en):
    empty = EmojiRegistry()
    embed = build_fissure_embed(_board(now), en, empty)
    desc = embed.description or ""
    # No emoji markup present, but the era name still shows.
    assert "<:" not in desc
    assert "Lith" in desc
    assert "Neo" in desc
