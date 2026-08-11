"""Active-alert extraction for the vendors embed.

Every currently-active alert is surfaced (Warframe rarely runs more than one or
two at a time, usually event chores like Dog Days → Nakak Pearls). We only drop
alerts whose window has already closed.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class AlertEntry:
    reward: str  # display reward, e.g. "375x Nakak Pearls"
    node: str  # "Outer Terminus (Pluto)"
    mission_type: str  # "Sabotage" (may be empty)
    expiry: datetime  # UTC


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def _reward_text(reward: dict[str, Any]) -> str:
    """Human reward string — plain ``items`` plus ``countedItems`` (with their
    count), falling back to a credits amount when there are no item rewards."""
    parts: list[str] = [str(n) for n in (reward.get("items") or []) if n]
    for ci in reward.get("countedItems") or []:
        if not isinstance(ci, dict):
            continue
        item_type = ci.get("type")
        if not item_type:
            continue
        count = ci.get("count") or 1
        parts.append(
            f"{count}x {item_type}" if isinstance(count, int) and count > 1 else str(item_type)
        )
    if parts:
        return ", ".join(parts)
    credits = reward.get("credits")
    if isinstance(credits, int) and credits > 0:
        return f"{credits:,} credits"
    return "reward"


def active_alerts(
    raw: list[dict[str, Any]] | None, now: datetime | None = None
) -> list[AlertEntry]:
    """All still-active alerts from a raw warframestat ``/alerts`` payload,
    sorted by soonest expiry. Only already-expired alerts are dropped."""
    now = now or datetime.now(timezone.utc)
    out: list[AlertEntry] = []
    for alert in raw or []:
        if not isinstance(alert, dict):
            continue
        expiry = _parse_dt(alert.get("expiry"))
        if expiry is None or expiry <= now:
            continue
        mission = alert.get("mission") or {}
        reward = mission.get("reward") or {}
        out.append(
            AlertEntry(
                reward=_reward_text(reward),
                node=str(mission.get("node") or "?"),
                mission_type=str(mission.get("type") or ""),
                expiry=expiry,
            )
        )
    out.sort(key=lambda a: a.expiry)
    return out
