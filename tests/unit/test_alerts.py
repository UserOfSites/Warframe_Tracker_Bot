"""Notable-alert filtering + the vendors-embed Alerts section."""

from datetime import datetime, timedelta, timezone

import pytest

from titania.domain.alerts import notable_alerts
from titania.domain.baro import BaroBoard, VoidTraderState
from titania.i18n.translator import Translator
from titania.presentation.vendor_embed import build_vendors_embed
from titania.services.emoji_registry import EmojiRegistry

UTC = timezone.utc
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def _alert(reward_items=None, counted=None, *, node="Outer Terminus (Pluto)",
           mtype="Sabotage", expiry=None) -> dict:
    return {
        "expiry": (expiry or (NOW + timedelta(hours=6))).isoformat().replace("+00:00", "Z"),
        "mission": {
            "node": node,
            "type": mtype,
            "reward": {
                "items": reward_items or [],
                "countedItems": counted or [],
                "credits": 50000,
            },
        },
    }


# --- filtering ----------------------------------------------------------------


def test_notable_keeps_potato_forma_exilus():
    raw = [
        _alert(["Orokin Reactor Blueprint"]),
        _alert(["Orokin Catalyst"]),
        _alert(["Forma Blueprint"]),
        _alert(["Exilus Weapon Adapter Blueprint"]),
    ]
    out = notable_alerts(raw, NOW)
    assert len(out) == 4
    assert {"Orokin Reactor Blueprint", "Orokin Catalyst", "Forma Blueprint",
            "Exilus Weapon Adapter Blueprint"} == {a.reward for a in out}


def test_notable_drops_the_usual_junk():
    raw = [
        _alert(["Braton Blueprint"]),                       # weapon part
        _alert(counted=[{"count": 1, "type": "Fieldron"}]),
        _alert(counted=[{"count": 1, "type": "Detonite Injector"}]),
        _alert(counted=[{"count": 1, "type": "Mutagen Mass"}]),
        _alert(counted=[{"count": 350, "type": "Nakak Pearls"}]),  # event currency
    ]
    assert notable_alerts(raw, NOW) == []


def test_notable_drops_expired_and_sorts_by_expiry():
    raw = [
        _alert(["Forma"], expiry=NOW - timedelta(minutes=1)),          # expired
        _alert(["Orokin Catalyst"], expiry=NOW + timedelta(hours=8)),
        _alert(["Orokin Reactor"], expiry=NOW + timedelta(hours=2)),
    ]
    out = notable_alerts(raw, NOW)
    assert [a.reward for a in out] == ["Orokin Reactor", "Orokin Catalyst"]


def test_notable_mixed_reward_reports_only_the_notable_item():
    raw = [_alert(["Braton Blueprint", "Orokin Catalyst"])]
    out = notable_alerts(raw, NOW)
    assert len(out) == 1
    assert out[0].reward == "Orokin Catalyst"


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


def test_alerts_section_absent_when_no_notable_alerts(en, registry):
    embed = build_vendors_embed(_board(), en, registry, alerts=[])
    assert "Alerts" not in (embed.description or "")


def test_alerts_section_present_with_notable_alert(en, registry):
    alerts = notable_alerts([_alert(["Orokin Reactor Blueprint"])], NOW)
    embed = build_vendors_embed(_board(), en, registry, alerts=alerts)
    desc = embed.description or ""
    assert "Alerts" in desc
    assert "Orokin Reactor Blueprint" in desc
    assert "Outer Terminus (Pluto)" in desc
