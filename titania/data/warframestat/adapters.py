from datetime import datetime, timezone
from typing import Any

from titania.domain.era import ERA_TIER, Era
from titania.domain.fissure import Fissure
from titania.domain.mission_type import parse_mission_type


def _parse_node(raw: str) -> tuple[str, str]:
    """warframestat returns 'Augustus (Mars)'; we split into ('Augustus', 'Mars')."""
    if "(" in raw and raw.endswith(")"):
        node, _, planet = raw.partition("(")
        return node.strip(), planet[:-1].strip()
    return raw.strip(), ""


def _parse_expiry(raw: str) -> datetime:
    # warframestat uses ISO 8601 with trailing 'Z'
    cleaned = raw.replace("Z", "+00:00")
    return datetime.fromisoformat(cleaned).astimezone(timezone.utc)


def _parse_era(raw: str) -> Era:
    try:
        return Era(raw)
    except ValueError:
        # Fall back on case-insensitive lookup.
        for e in Era:
            if e.value.lower() == raw.strip().lower():
                return e
        raise


def adapt_fissure(raw: dict[str, Any]) -> Fissure:
    era = _parse_era(raw["tier"])
    node, planet = _parse_node(raw.get("node", ""))
    return Fissure(
        era=era,
        mission_type=parse_mission_type(raw.get("missionType") or raw.get("mission") or ""),
        node=node,
        planet=planet,
        expires_at=_parse_expiry(raw["expiry"]),
        is_steel_path=bool(raw.get("isHard", False)),
        is_hard=bool(raw.get("isStorm", False)),
        tier=int(raw.get("tierNum") or ERA_TIER[era]),
    )


def adapt_fissures(payload: list[dict[str, Any]]) -> list[Fissure]:
    # Anchor once per call so every entry is judged against the same clock.
    now = datetime.now(timezone.utc)
    out: list[Fissure] = []
    for item in payload:
        if item.get("expired"):
            continue
        try:
            fissure = adapt_fissure(item)
        except (KeyError, ValueError):
            # Skip malformed entries silently; upstream occasionally ships partial rows.
            continue
        # Don't rely on upstream's `expired` flag alone — warframestat has been
        # observed serving a frozen worldstate where every fissure's `expiry`
        # is hours in the past yet `expired` stays false. Ingesting those would
        # pin the board to a wall of dead fissures (all timers in the past) and,
        # because the cache anchors its validity to the soonest expiry, would
        # never let a fresh window take over. Drop anything already expired.
        if fissure.expires_at <= now:
            continue
        out.append(fissure)
    return out
