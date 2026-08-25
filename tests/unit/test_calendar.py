from datetime import datetime, timezone

from titania.data.fake.source import InMemoryFakeSource
from titania.domain.calendar import notable_calendar_rewards
from titania.services.calendar_service import CalendarService

_NOW = datetime(2050, 6, 1, tzinfo=timezone.utc)


def _season(days, activation="1999-01-01T00:00:00.000Z", expiry="2099-01-01T00:00:00.000Z"):
    return {"activation": activation, "expiry": expiry, "season": "Winter", "days": days}


def _day(date, *rewards):
    return {"date": date, "events": [{"type": "Big Prize!", "reward": r} for r in rewards]}


def test_keeps_only_shards_and_boosters():
    raw = _season([
        _day("1999-01-13T00:00:00.000Z", "Weapon Primary Arcane Unlocker"),  # drop
        _day("1999-01-21T00:00:00.000Z", "3 Day Mod Drop Chance Booster"),   # booster
        _day("1999-02-16T00:00:00.000Z", "Arcane Enhancements", "Archon Crystal Boreal"),  # shard
        _day("1999-02-20T00:00:00.000Z", "6,000 Endo"),                      # drop
    ])
    out = notable_calendar_rewards(raw, now=_NOW)
    assert [(r.kind, r.reward) for r in out] == [
        ("booster", "3 Day Mod Drop Chance Booster"),
        ("shard", "Archon Crystal Boreal"),
    ]


def test_day_label_is_month_and_day_without_zero_pad():
    out = notable_calendar_rewards(
        _season([_day("1999-01-05T00:00:00.000Z", "3 Day Resource Booster")]), now=_NOW
    )
    assert out[0].day == "Jan 5"


def test_empty_when_season_not_yet_active():
    raw = _season(
        [_day("1999-01-21T00:00:00.000Z", "3 Day Mod Drop Chance Booster")],
        activation="2099-01-01T00:00:00.000Z",  # starts in the future
    )
    assert notable_calendar_rewards(raw, now=_NOW) == []


def test_empty_when_season_expired():
    raw = _season(
        [_day("1999-01-21T00:00:00.000Z", "3 Day Mod Drop Chance Booster")],
        expiry="2000-01-01T00:00:00.000Z",  # already ended
    )
    assert notable_calendar_rewards(raw, now=_NOW) == []


def test_empty_on_missing_or_malformed_payload():
    assert notable_calendar_rewards(None, now=_NOW) == []
    assert notable_calendar_rewards({}, now=_NOW) == []
    assert notable_calendar_rewards({"days": "nope"}, now=_NOW) == []


def test_season_with_no_notable_rewards_is_empty():
    raw = _season([_day("1999-01-13T00:00:00.000Z", "Exilus Adapter", "6,000 Endo")])
    assert notable_calendar_rewards(raw, now=_NOW) == []


async def test_service_filters_fake_source_fixture():
    rewards = await CalendarService(InMemoryFakeSource.from_fixtures()).notable()
    kinds = {r.kind for r in rewards}
    names = {r.reward for r in rewards}
    assert kinds == {"booster", "shard"}
    assert "Archon Crystal Boreal" in names
    # The non-notable arcane in the fixture is filtered out.
    assert "Arcane Enhancements" not in names


async def test_service_swallows_source_errors():
    class _Boom:
        async def fetch_calendar(self):
            raise RuntimeError("down")

    assert await CalendarService(_Boom()).notable() == []


# --- embed rendering ---------------------------------------------------------
from titania.domain.baro import BaroBoard, VoidTraderState  # noqa: E402
from titania.domain.calendar import CalendarReward  # noqa: E402
from titania.i18n.translator import Translator  # noqa: E402
from titania.presentation.vendor_embed import build_vendors_embed  # noqa: E402
from titania.services.emoji_registry import EmojiRegistry  # noqa: E402


def _board():
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    state = VoidTraderState(
        character="Baro Ki'Teer", location="Larunda Relay (Mercury)",
        activation=now, expiry=now, inventory=(),
    )
    return BaroBoard(state=state, enriched_inventory=(), generated_at=now)


def test_embed_renders_calendar_block_when_rewards_present():
    rewards = [
        CalendarReward(day="Jan 21", reward="3 Day Mod Drop Chance Booster", kind="booster"),
        CalendarReward(day="Feb 16", reward="Archon Crystal Boreal", kind="shard"),
    ]
    embed = build_vendors_embed(_board(), Translator("en"), EmojiRegistry(), calendar=rewards)
    desc = embed.description or ""
    assert "Calendar (1999)" in desc
    assert "3 Day Mod Drop Chance Booster" in desc
    assert "Feb 16 · Archon Crystal Boreal" in desc


def test_embed_omits_calendar_block_when_empty():
    embed = build_vendors_embed(_board(), Translator("en"), EmojiRegistry(), calendar=[])
    assert "Calendar" not in (embed.description or "")


def test_embed_uses_shard_icon_when_registered():
    class _Reg(EmojiRegistry):
        def __init__(self):
            super().__init__()
            self._markup = {"archon_shard_azure": "<:archon_shard_azure:9>"}

    rewards = [CalendarReward(day="Feb 16", reward="Archon Crystal Boreal", kind="shard")]
    embed = build_vendors_embed(_board(), Translator("en"), _Reg(), calendar=rewards)
    assert "<:archon_shard_azure:9>" in (embed.description or "")
