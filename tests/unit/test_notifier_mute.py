"""Regression tests for the *quiet mode* semantics of ``/mute``.

Before this change, muting bailed out of ``_process_user`` entirely — no
summary edits, no welcome, no alerts. That's too aggressive: users who mute
still want their persistent summary DM to keep tracking new fissures; they
just don't want the short "new fissure!" pings that also arrive.

The tests below drive ``_process_user`` with a stub bot and verify:
  1. A muted user with new matches gets ``_upsert_summary`` called but
     ``_send_alert`` NOT called.
  2. A non-muted user with the same matches gets *both* called.
  3. Toggling mute mid-flight flips the behaviour on the next tick.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from titania.domain.era import Era
from titania.domain.fissure import Fissure
from titania.domain.mission_type import MissionType
from titania.services.notifier import FissureNotifier


def _f(node: str) -> Fissure:
    return Fissure(
        era=Era.LITH,
        mission_type=MissionType.CAPTURE,
        node=node,
        planet="Void",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        is_steel_path=False,
        is_hard=False,
        tier=1,
    )


@dataclass
class _FakeBot:
    is_muted: bool = False
    subs_by_user: dict[int, list[tuple]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.user_preferences_repo = MagicMock()
        self.user_preferences_repo.is_muted = AsyncMock(
            side_effect=lambda _uid: self.is_muted
        )
        self.user_preferences_repo.has_been_welcomed = AsyncMock(return_value=True)
        self.user_preferences_repo.mark_welcomed = AsyncMock()
        self.subscriptions_repo = MagicMock()
        self.subscriptions_repo.list_subscribers_with_filters = AsyncMock(
            return_value=[]
        )
        self.user_notification_messages_repo = MagicMock()
        self.user_notification_messages_repo.get = AsyncMock(return_value=None)


@pytest.fixture
def bot():
    return _FakeBot()


@pytest.fixture
def notifier(bot):
    n = FissureNotifier(bot)
    # Stub the DM I/O so tests don't need Discord — we only care about which
    # of these got called and with what.
    n._upsert_summary = AsyncMock()  # type: ignore[method-assign]
    n._send_alert = AsyncMock()  # type: ignore[method-assign]
    return n


async def _fake_matches(notifier, subs, all_fissures):
    from titania.services.notifier import FissureTopic

    # Ignore the real matching logic — for these tests all fissures match
    # a single "fast_normal" topic.
    return {FissureTopic.FAST_NORMAL: all_fissures}


async def test_muted_user_gets_summary_update_but_no_alert(bot, notifier, monkeypatch):
    bot.is_muted = True
    monkeypatch.setattr(notifier, "_matches_for_user", lambda subs, f: {"topic": f})
    # Baseline so the change-detection path triggers on the next call.
    notifier._user_seen[42] = set()

    await notifier._process_user(42, subs=[], all_fissures=[_f("Hepit"), _f("Ukko")])

    notifier._upsert_summary.assert_awaited_once()  # summary keeps ticking
    notifier._send_alert.assert_not_awaited()       # but the ping is silenced


async def test_unmuted_user_gets_both_summary_and_alert(bot, notifier, monkeypatch):
    bot.is_muted = False
    monkeypatch.setattr(notifier, "_matches_for_user", lambda subs, f: {"topic": f})
    notifier._user_seen[42] = set()

    await notifier._process_user(42, subs=[], all_fissures=[_f("Hepit")])

    notifier._upsert_summary.assert_awaited_once()
    notifier._send_alert.assert_awaited_once()


async def test_toggling_mute_flips_alert_behaviour_next_tick(
    bot, notifier, monkeypatch
):
    monkeypatch.setattr(notifier, "_matches_for_user", lambda subs, f: {"topic": f})
    notifier._user_seen[42] = set()

    # Tick 1: not muted → both fire.
    bot.is_muted = False
    await notifier._process_user(42, subs=[], all_fissures=[_f("Hepit")])
    assert notifier._send_alert.await_count == 1

    # Tick 2: mute flipped on, new fissure → summary edits, alert does not.
    bot.is_muted = True
    await notifier._process_user(42, subs=[], all_fissures=[_f("Hepit"), _f("Ukko")])
    assert notifier._send_alert.await_count == 1  # unchanged
    assert notifier._upsert_summary.await_count == 2

    # Tick 3: unmuted, another new fissure → alert fires again.
    bot.is_muted = False
    await notifier._process_user(
        42, subs=[], all_fissures=[_f("Hepit"), _f("Ukko"), _f("Oxomoco")]
    )
    assert notifier._send_alert.await_count == 2
    assert notifier._upsert_summary.await_count == 3


async def test_muted_user_summary_untouched_when_nothing_changes(
    bot, notifier, monkeypatch
):
    """A muted user on a stable tick (no new matches) still shouldn't get
    an alert *and* shouldn't waste a summary edit."""
    bot.is_muted = True
    monkeypatch.setattr(notifier, "_matches_for_user", lambda subs, f: {"topic": f})
    from titania.services.notifier import _fissure_key

    fissures = [_f("Hepit")]
    notifier._user_seen[42] = {_fissure_key(f) for f in fissures}

    await notifier._process_user(42, subs=[], all_fissures=fissures)

    notifier._upsert_summary.assert_not_awaited()
    notifier._send_alert.assert_not_awaited()
