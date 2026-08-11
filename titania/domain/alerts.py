"""Notable-only alert filtering.

Warframe alerts these days are sparse and mostly event chores whose rewards are
the "usual" fare — weapon parts, Fieldron / Detonite Injector / Mutagen Mass,
credits, Endo, event currencies. We surface an alert in the vendors embed *only*
when its reward is something worth logging in for: an Orokin Reactor/Catalyst
("potato"), Forma, or an Exilus adapter. Everything else is dropped so the
section stays quiet until it actually matters.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

# Reward-name substrings (lowercased) considered notable. Substring match so
# blueprints count too ("Orokin Reactor Blueprint" → matches "orokin reactor").
_NOTABLE_SUBSTRINGS: tuple[str, ...] = (
    "forma",
    "orokin reactor",
    "orokin catalyst",
    "exilus adapter",
    "exilus weapon adapter",
)


@dataclass(frozen=True)
class NotableAlert:
    reward: str  # display reward, e.g. "Orokin Reactor Blueprint"
    node: str  # "Outer Terminus (Pluto)"
    mission_type: str  # "Sabotage" (may be empty)
    expiry: datetime  # UTC


def _is_notable(name: str) -> bool:
    lc = name.lower()
    return any(s in lc for s in _NOTABLE_SUBSTRINGS)


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def _reward_names(reward: dict[str, Any]) -> list[str]:
    """Flatten a warframestat ``reward`` into display strings — plain ``items``
    plus ``countedItems`` (prefixed with their count when > 1)."""
    names: list[str] = [str(n) for n in (reward.get("items") or []) if n]
    for ci in reward.get("countedItems") or []:
        if not isinstance(ci, dict):
            continue
        item_type = ci.get("type")
        if not item_type:
            continue
        count = ci.get("count") or 1
        names.append(f"{count}x {item_type}" if isinstance(count, int) and count > 1 else str(item_type))
    return names


def notable_alerts(
    raw: list[dict[str, Any]] | None, now: datetime | None = None
) -> list[NotableAlert]:
    """Filter a raw warframestat ``/alerts`` payload down to still-active alerts
    whose reward includes a notable item, sorted by soonest expiry."""
    now = now or datetime.now(timezone.utc)
    out: list[NotableAlert] = []
    for alert in raw or []:
        if not isinstance(alert, dict):
            continue
        mission = alert.get("mission") or {}
        reward = mission.get("reward") or {}
        names = _reward_names(reward)
        notable = [n for n in names if _is_notable(n)]
        if not notable:
            continue
        expiry = _parse_dt(alert.get("expiry"))
        if expiry is None or expiry <= now:
            continue
        out.append(
            NotableAlert(
                reward=", ".join(notable),
                node=str(mission.get("node") or "?"),
                mission_type=str(mission.get("type") or ""),
                expiry=expiry,
            )
        )
    out.sort(key=lambda a: a.expiry)
    return out
