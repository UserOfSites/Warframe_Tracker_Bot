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


def _defence_board(now: datetime, node: str, is_steel_path: bool) -> FissureBoard:
    return FissureBoard(
        normal=[],
        steel_path=[],
        dojoshare=[],
        next_resets=[],
        generated_at=now,
        defences=[
            _fissure(Era.LITH, MissionType.DEFENSE, node, "Uranus",
                     now + timedelta(minutes=20), is_steel_path=is_steel_path),
        ],
    )


def _defences_line(desc: str) -> str:
    """The single fissure row under the Defences section header."""
    lines = desc.split("\n")
    idx = next(i for i, ln in enumerate(lines) if ln.strip("* ") == "Defences")
    return lines[idx + 1]


def test_steel_path_defence_row_shows_steel_essence_marker(now, en, registry):
    """A Steel Path Defense fissure must carry the steel-path (Steel Essence)
    marker before the name, so SP entries are distinguishable in the mixed
    Normal+SP Defences section."""
    embed = build_fissure_embed(_defence_board(now, "Stephano", True), en, registry)
    row = _defences_line(embed.description or "")
    assert "<:steel_path:6>" in row
    # The marker leads the row, ahead of the era name and node.
    assert row.index("<:steel_path:6>") < row.index("Stephano")


def test_normal_defence_row_has_no_steel_essence_marker(now, en, registry):
    embed = build_fissure_embed(_defence_board(now, "Stephano", False), en, registry)
    row = _defences_line(embed.description or "")
    assert "Stephano" in row
    assert "<:steel_path:6>" not in row


def test_quality_stars_apply_to_defences_section(now, en, registry):
    excellent = build_fissure_embed(
        _defence_board(now, "Stephano", True), en, registry,
        excellent_nodes=frozenset({"Stephano"}),
    )
    assert "🌟" in _defences_line(excellent.description or "")
    good = build_fissure_embed(
        _defence_board(now, "Hydron", False), en, registry,
        good_nodes=frozenset({"Hydron"}),
    )
    assert "⭐" in _defences_line(good.description or "")


def test_registry_missing_emoji_falls_back_to_era_text(now, en):
    empty = EmojiRegistry()
    embed = build_fissure_embed(_board(now), en, empty)
    desc = embed.description or ""
    # No emoji markup present, but the era name still shows.
    assert "<:" not in desc
    assert "Lith" in desc
    assert "Neo" in desc


def test_cascade_section_renders_with_icon(now, en):
    from titania.presentation.embeds import build_fissure_embed as _build

    class _Reg(_StubRegistry):
        def __init__(self):
            super().__init__()
            self._markup["void_cascade"] = "<:void_cascade:9>"

    board = FissureBoard(
        normal=[], steel_path=[], dojoshare=[],
        cascade=[_fissure(Era.OMNIA, MissionType.OTHER, "Tuvul Commons", "Zariman",
                          now + timedelta(minutes=20), is_steel_path=True)],
        next_resets=[], generated_at=now,
    )
    desc = _build(board, en, _Reg()).description or ""
    assert "<:void_cascade:9> Void Cascade" in desc
    assert "Tuvul Commons" in desc


def test_cascade_section_shows_empty_hint(now, en, registry):
    board = FissureBoard(
        normal=[], steel_path=[], dojoshare=[], cascade=[],
        next_resets=[], generated_at=now,
    )
    desc = build_fissure_embed(board, en, registry).description or ""
    assert "No Steel Path Void Cascade right now." in desc
