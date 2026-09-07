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


def test_current_and_next_frames_from_schedule():
    raw = _raw([
        {"expiry": "2026-08-06T18:00:00.000Z", "item": "M P V Old Prime Pack"},  # past
        {"expiry": "2026-09-03T18:00:00.000Z", "item": "M P V Revenant Baruuk Prime Dual Pack"},
        {"expiry": "2026-10-01T18:00:00.000Z", "item": "M P V Banshee Mirage Prime Dual Pack"},
    ])
    rot = varzia_rotation(raw, now=_NOW)
    assert rot is not None
    assert rot.current_frames == ("Revenant", "Baruuk")  # MPV/Prime/Pack stripped
    assert rot.next_frames == ("Banshee", "Mirage")
    assert rot.expiry == datetime(2026, 9, 3, 18, tzinfo=timezone.utc)


def test_single_frame_rotation():
    raw = _raw([{"expiry": "2026-09-03T18:00:00.000Z", "item": "M P V Oberon Prime Single Pack"}])
    rot = varzia_rotation(raw, now=_NOW)
    assert rot is not None
    assert rot.current_frames == ("Oberon",)


def test_next_is_none_when_only_current_announced():
    raw = _raw([{"expiry": "2026-09-03T18:00:00.000Z", "item": "M P V Revenant Baruuk Prime Dual Pack"}])
    rot = varzia_rotation(raw, now=_NOW)
    assert rot is not None
    assert rot.current_frames == ("Revenant", "Baruuk")
    assert rot.next_frames is None


def test_none_when_window_expired():
    raw = _raw([], expiry="2020-01-01T00:00:00.000Z")
    assert varzia_rotation(raw, now=_NOW) is None


def test_none_on_missing_payload():
    assert varzia_rotation(None, now=_NOW) is None
    assert varzia_rotation({}, now=_NOW) is None


def test_current_empty_when_schedule_absent_but_window_active():
    rot = varzia_rotation(_raw([]), now=_NOW)
    assert rot is not None
    assert rot.current_frames == ()
    assert rot.next_frames is None


async def test_service_reads_fake_fixture():
    rot = await VarziaService(InMemoryFakeSource.from_fixtures()).rotation()
    assert rot is not None
    assert rot.current_frames == ("Revenant", "Baruuk")
    assert rot.next_frames == ("Banshee", "Mirage")


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


def _rot(next_frames):
    return VarziaRotation(
        location="Maroo's Bazaar (Mars)",
        expiry=datetime(2026, 9, 3, 18, tzinfo=timezone.utc),
        current_frames=("Revenant", "Baruuk"),
        current_featured="Revenant Baruuk Prime Dual Pack",
        next_frames=next_frames,
    )


def test_embed_renders_varzia_on_top_with_frames():
    desc = build_vendors_embed(
        _board(), Translator("en"), EmojiRegistry(), varzia=_rot(("Banshee", "Mirage"))
    ).description or ""
    assert "Varzia aya rotation" in desc
    assert "Revenant, Baruuk" in desc
    assert "Next Varzia rotation" in desc
    assert "Banshee, Mirage" in desc
    # Varzia sits above Baro.
    assert desc.index("Varzia aya rotation") < desc.index("Baro")


def test_embed_varzia_next_countdown_when_unannounced():
    desc = build_vendors_embed(
        _board(), Translator("en"), EmojiRegistry(), varzia=_rot(None)
    ).description or ""
    assert "Next Varzia rotation" in desc
    assert "Not yet announced" in desc


def test_embed_omits_varzia_when_none():
    desc = build_vendors_embed(_board(), Translator("en"), EmojiRegistry(), varzia=None).description or ""
    assert "Varzia" not in desc


# --- source-down notice ------------------------------------------------------
from titania.domain.calendar import CalendarReward as _CR  # noqa: E402


def test_embed_shows_down_notice_when_source_unavailable():
    # Even with Varzia/calendar data available, an unavailable source shows the
    # notice and hides those sections (can't tell "empty" from "missing").
    rot = _rot(("Banshee", "Mirage"))
    cal = [_CR(day="Jan 21", reward="3 Day Mod Drop Chance Booster", kind="booster")]
    desc = build_vendors_embed(
        _board(), Translator("en"), EmojiRegistry(),
        varzia=rot, calendar=cal, source_available=False,
    ).description or ""
    assert "temporarily\ndown" in desc or "temporarily down" in desc
    assert "Varzia rotation, calendar, alerts & invasions" in desc
    assert "Banshee, Mirage" not in desc       # varzia section hidden
    assert "Mod Drop Chance Booster" not in desc  # calendar hidden
    # Baro / Teshin still render.
    assert "Baro Ki'Teer" in desc


def test_embed_shows_sections_when_source_available():
    rot = _rot(("Banshee", "Mirage"))
    desc = build_vendors_embed(
        _board(), Translator("en"), EmojiRegistry(),
        varzia=rot, source_available=True,
    ).description or ""
    assert "Varzia aya rotation" in desc
    assert "temporarily down" not in desc
