"""Notable-invasion filtering + the vendors-embed Invasions section."""

from datetime import datetime, timedelta, timezone

import pytest

from titania.domain.baro import BaroBoard, VoidTraderState
from titania.domain.invasions import image_name_from_thumbnail, notable_invasions
from titania.i18n.translator import Translator
from titania.presentation.vendor_embed import build_vendors_embed
from titania.services.emoji_registry import EmojiRegistry

UTC = timezone.utc
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def _side(reward_items=None, counted=None, thumbnail=""):
    return {"reward": {"items": reward_items or [], "countedItems": counted or [],
                       "thumbnail": thumbnail}}


def _invasion(attacker=None, defender=None, *, node="Rusalka (Sedna)", completed=False):
    return {
        "node": node,
        "completed": completed,
        "attacker": attacker or _side(),
        "defender": defender or _side(),
    }


# --- filtering ----------------------------------------------------------------


def test_notable_invasion_kept_with_reward_icon():
    raw = [_invasion(
        attacker=_side(counted=[{"count": 3, "type": "Fieldron"}], thumbnail="https://cdn/img/fieldron.png"),
        defender=_side(["Orokin Catalyst Blueprint"], thumbnail="https://cdn/img/orokin-catalyst.png"),
    )]
    out = notable_invasions(raw)
    assert len(out) == 1
    assert out[0].reward == "Orokin Catalyst Blueprint"
    assert out[0].node == "Rusalka (Sedna)"
    assert out[0].image_name == "orokin-catalyst.png"


def test_notable_invasion_matches_forma_reactor_exilus():
    raw = [
        _invasion(defender=_side(["Forma Blueprint"])),
        _invasion(defender=_side(["Orokin Reactor Blueprint"])),
        _invasion(defender=_side(["Exilus Warframe Adapter Blueprint"])),
    ]
    assert {i.reward for i in notable_invasions(raw)} == {
        "Forma Blueprint", "Orokin Reactor Blueprint", "Exilus Warframe Adapter Blueprint",
    }


def test_junk_invasions_dropped():
    raw = [_invasion(
        attacker=_side(counted=[{"count": 3, "type": "Fieldron"}]),
        defender=_side(counted=[{"count": 3, "type": "Detonite Injector"}]),
    )]
    assert notable_invasions(raw) == []


def test_completed_invasions_dropped():
    raw = [_invasion(defender=_side(["Forma"]), completed=True)]
    assert notable_invasions(raw) == []


def test_image_name_from_thumbnail():
    assert image_name_from_thumbnail("https://cdn.warframestat.us/img/orokin-reactor.png") == "orokin-reactor.png"
    assert image_name_from_thumbnail("") is None
    assert image_name_from_thumbnail(None) is None


# --- embed section ------------------------------------------------------------


def _board() -> BaroBoard:
    state = VoidTraderState(
        character="Baro Ki'Teer", location="Larunda Relay (Mercury)",
        activation=NOW + timedelta(days=5), expiry=NOW + timedelta(days=7),
        inventory=(),
    )
    return BaroBoard(state=state, enriched_inventory=(), generated_at=NOW)


@pytest.fixture
def en() -> Translator:
    return Translator("en")


@pytest.fixture
def registry() -> EmojiRegistry:
    return EmojiRegistry()


def test_invasions_section_absent_when_none_notable(en, registry):
    embed = build_vendors_embed(_board(), en, registry, invasions=[])
    assert "Invasions" not in (embed.description or "")


def test_invasions_section_uses_reward_icon(en, registry):
    invasions = notable_invasions([_invasion(
        defender=_side(["Orokin Reactor Blueprint"], thumbnail="https://cdn/img/orokin-reactor.png"),
    )])
    icons = {"orokin-reactor.png": "<:wf_orokin_reactor:99>"}
    embed = build_vendors_embed(
        _board(), en, registry, invasions=invasions, invasion_icons=icons,
    )
    desc = embed.description or ""
    assert "Invasions" in desc
    assert "Orokin Reactor Blueprint" in desc
    assert "<:wf_orokin_reactor:99>" in desc  # the fetched reward icon leads the line
