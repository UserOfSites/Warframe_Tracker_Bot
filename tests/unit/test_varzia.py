from datetime import datetime, timezone

from titania.data.fake.source import InMemoryFakeSource
from titania.domain.baro import BaroBoard, VoidTraderState
from titania.domain.varzia import VarziaRotation, varzia_rotation
from titania.i18n.translator import Translator
from titania.presentation.vendor_embed import build_vendors_embed
from titania.services.emoji_registry import EmojiRegistry
from titania.services.varzia_service import VarziaService

_NOW = datetime(2026, 8, 25, tzinfo=timezone.utc)


def _raw(schedule, expiry="2026-09-03T18:00:00.000Z", location="Maroo's Bazaar (Mars)"):
    return {
        "location": location,
        "activation": "2026-08-06T18:00:00.000Z",
        "expiry": expiry,
        "inventory": [],
        "schedule": schedule,
    }


def test_current_and_next_from_schedule():
    raw = _raw([
        {"expiry": "2026-08-06T18:00:00.000Z", "item": "M P V Old Prime Pack"},  # past
        {"expiry": "2026-09-03T18:00:00.000Z", "item": "M P V Revenant Baruuk Prime Dual Pack"},
        {"expiry": "2026-10-01T18:00:00.000Z", "item": "M P V Banshee Mirage Prime Dual Pack"},
    ])
    rot = varzia_rotation(raw, now=_NOW)
    assert rot is not None
    assert rot.current_featured == "Revenant Baruuk Prime Dual Pack"  # MPV prefix stripped
    assert rot.next_featured == "Banshee Mirage Prime Dual Pack"
    assert rot.expiry == datetime(2026, 9, 3, 18, tzinfo=timezone.utc)
    assert rot.next_expiry == datetime(2026, 10, 1, 18, tzinfo=timezone.utc)


def test_next_is_none_when_only_current_announced():
    raw = _raw([{"expiry": "2026-09-03T18:00:00.000Z", "item": "M P V Revenant Baruuk Prime Dual Pack"}])
    rot = varzia_rotation(raw, now=_NOW)
    assert rot is not None
    assert rot.current_featured == "Revenant Baruuk Prime Dual Pack"
    assert rot.next_featured is None
    assert rot.next_expiry is None


def test_none_when_window_expired():
    raw = _raw([], expiry="2020-01-01T00:00:00.000Z")
    assert varzia_rotation(raw, now=_NOW) is None


def test_none_on_missing_payload():
    assert varzia_rotation(None, now=_NOW) is None
    assert varzia_rotation({}, now=_NOW) is None


def test_current_empty_when_schedule_absent_but_window_active():
    rot = varzia_rotation(_raw([]), now=_NOW)
    assert rot is not None
    assert rot.current_featured == ""
    assert rot.next_featured is None


async def test_service_reads_fake_fixture():
    rot = await VarziaService(InMemoryFakeSource.from_fixtures()).rotation()
    assert rot is not None
    assert rot.current_featured == "Revenant Baruuk Prime Dual Pack"
    assert rot.next_featured == "Banshee Mirage Prime Dual Pack"


async def test_service_swallows_errors():
    class _Boom:
        async def fetch_vault_trader(self):
            raise RuntimeError("down")

    assert await VarziaService(_Boom()).rotation() is None


# --- embed rendering ---------------------------------------------------------
def _board():
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    state = VoidTraderState(
        character="Baro Ki'Teer", location="Larunda Relay (Mercury)",
        activation=now, expiry=now, inventory=(),
    )
    return BaroBoard(state=state, enriched_inventory=(), generated_at=now)


def test_embed_renders_varzia_with_current_and_next():
    rot = VarziaRotation(
        location="Maroo's Bazaar (Mars)",
        expiry=datetime(2026, 9, 3, 18, tzinfo=timezone.utc),
        current_featured="Revenant Baruuk Prime Dual Pack",
        next_featured="Banshee Mirage Prime Dual Pack",
        next_expiry=datetime(2026, 10, 1, 18, tzinfo=timezone.utc),
    )
    desc = build_vendors_embed(_board(), Translator("en"), EmojiRegistry(), varzia=rot).description or ""
    assert "Varzia" in desc and "Prime Resurgence" in desc
    assert "Revenant Baruuk Prime Dual Pack" in desc
    assert "Next: **Banshee Mirage Prime Dual Pack**" in desc


def test_embed_omits_varzia_when_none():
    desc = build_vendors_embed(_board(), Translator("en"), EmojiRegistry(), varzia=None).description or ""
    assert "Varzia" not in desc
