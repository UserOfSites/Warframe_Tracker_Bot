"""Notable-reward extraction for the 1999 (Höllvania) calendar.

DE's seasonal calendar awards a mix of arcanes, adapters, Endo, boosters and
Archon shards across the season's days. For the vendors summary we surface only
the two reward kinds worth planning around — **Archon shards** and **boosters**
— and only while the season is actually running. Everything else is dropped, so
the whole block is omitted when a season carries none.

warframestat parses DE's raw ``KnownCalendarSeasons`` into friendly names
(``"Archon Crystal Boreal"``, ``"3 Day Mod Drop Chance Booster"``), so we match
on the display name rather than raw Lotus paths. Day dates are the in-fiction
1999 dates; the season's real-time window lives in ``activation``/``expiry``.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

RewardKind = Literal["shard", "booster"]


@dataclass(frozen=True)
class CalendarReward:
    day: str  # in-fiction day label, e.g. "Jan 13" (may be empty if unparseable)
    reward: str  # friendly reward name, e.g. "Archon Crystal Boreal"
    kind: RewardKind


def _parse_dt(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def _classify(name: str) -> RewardKind | None:
    lc = name.lower()
    # Archon shards ship as "Archon Crystal <colour>" in the calendar; also match
    # the "Archon Shard" phrasing defensively in case naming shifts.
    if "archon" in lc and ("crystal" in lc or "shard" in lc):
        return "shard"
    if "booster" in lc:
        return "booster"
    return None


def _day_label(date: datetime | None) -> str:
    if date is None:
        return ""
    # "Jan 13" — strip the zero-padded day (e.g. "Jan 05" -> "Jan 5").
    return f"{date:%b} {date.day}"


def notable_calendar_rewards(
    raw: dict[str, Any] | None, now: datetime | None = None
) -> list[CalendarReward]:
    """Archon-shard and booster rewards for the currently-active calendar
    season, in calendar-day order. Empty if the payload is missing, the season
    isn't running, or it carries no such rewards."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(raw, dict):
        return []
    # Only surface a season that is actually live right now.
    activation = _parse_dt(raw.get("activation"))
    expiry = _parse_dt(raw.get("expiry"))
    if activation is not None and now < activation:
        return []
    if expiry is not None and now >= expiry:
        return []

    out: list[CalendarReward] = []
    for day in raw.get("days") or []:
        if not isinstance(day, dict):
            continue
        label = _day_label(_parse_dt(day.get("date")))
        for event in day.get("events") or []:
            if not isinstance(event, dict):
                continue
            reward = event.get("reward")
            if not isinstance(reward, str) or not reward:
                continue
            kind = _classify(reward)
            if kind is None:
                continue
            out.append(CalendarReward(day=label, reward=reward, kind=kind))
    return out
