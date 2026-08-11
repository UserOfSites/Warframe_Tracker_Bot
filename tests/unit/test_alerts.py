"""Active-alert extraction + the vendors-embed Alerts section."""

from datetime import datetime, timedelta, timezone

import pytest

from titania.domain.alerts import active_alerts
from titania.domain.baro import BaroBoard, VoidTraderState
from titania.i18n.translator import Translator
from titania.presentation.vendor_embed import build_vendors_embed
from titania.services.emoji_registry import EmojiRegistry

UTC = timezone.utc
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def _alert(reward_items=None, counted=None, credits=0, *,
           node="Outer Terminus (Pluto)", mtype="Sabotage", expiry=None) -> dict:
    return {
        "expiry": (expiry or (NOW + timedelta(hours=6))).isoformat().replace("+00:00", "Z"),
        "mission": {
            "node": node,
            "type": mtype,
            "reward": {
                "items": reward_items or [],
                "countedItems": counted or [],
                "credits": credits,
            },
        },
    }


# --- extraction ---------------------------------------------------------------


def test_all_active_alerts_are_shown():
    raw = [
        _alert(counted=[{"count": 375, "type": "Nakak Pearls"}]),  # Dog Days event
        _alert(["Braton Blueprint"]),                              # weapon part
        _alert(["Orokin Reactor Blueprint"]),                      # potato
    ]
    out = active_alerts(raw, NOW)
    assert len(out) == 3
    assert "375x Nakak Pearls" in {a.reward for a in out}
    assert "Braton Blueprint" in {a.reward for a in out}


def test_counted_reward_shows_quantity():
    out = active_alerts([_alert(counted=[{"count": 375, "type": "Nakak Pearls"}])], NOW)
    assert out[0].reward == "375x Nakak Pearls"


def test_credits_only_reward_falls_back_to_credits():
    out = active_alerts([_alert(credits=50000)], NOW)
    assert out[0].reward == "50,000 credits"


def test_expired_alerts_dropped_and_sorted_by_expiry():
    raw = [
        _alert(["A"], expiry=NOW - timedelta(minutes=1)),        # expired
        _alert(["B"], expiry=NOW + timedelta(hours=8)),
        _alert(["C"], expiry=NOW + timedelta(hours=2)),
    ]
    out = active_alerts(raw, NOW)
    assert [a.reward for a in out] == ["C", "B"]


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


def test_alerts_section_absent_when_no_active_alerts(en, registry):
    embed = build_vendors_embed(_board(), en, registry, alerts=[])
    assert "Alerts" not in (embed.description or "")


def test_alerts_section_shows_event_reward(en, registry):
    alerts = active_alerts([_alert(counted=[{"count": 375, "type": "Nakak Pearls"}])], NOW)
    embed = build_vendors_embed(_board(), en, registry, alerts=alerts)
    desc = embed.description or ""
    assert "Alerts" in desc
    assert "375x Nakak Pearls" in desc
    assert "Outer Terminus (Pluto)" in desc
