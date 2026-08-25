"""Varzia (Prime Resurgence) rotation extraction for the vendors embed.

Varzia sits permanently at Maroo's Bazaar and rotates a set of unvaulted Prime
packs roughly monthly. warframestat's parsed ``/vaultTrader`` gives the current
window (``activation``/``expiry``) plus a ``schedule`` — one ``{expiry, item}``
per rotation, including future ones once DE announces them. So the current
rotation is the soonest-expiring future schedule entry (its expiry matches the
trader's window end), and the *next* rotation, if announced, is the one after.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


# Words in a pack name that aren't the Warframe itself. Whatever remains after
# dropping these is the frame list ("Revenant Baruuk Prime Dual Pack" ->
# Revenant, Baruuk). Prime frame names are all single words, so a plain split is
# safe.
_PACK_DESCRIPTORS = frozenset({
    "prime", "dual", "single", "triple", "pack", "accessories", "accessory",
    "set", "armor", "armour",
})


@dataclass(frozen=True)
class VarziaRotation:
    location: str
    expiry: datetime  # when the current rotation ends
    current_frames: tuple[str, ...]  # e.g. ("Revenant", "Baruuk")
    current_featured: str  # raw headline, e.g. "Revenant Baruuk Prime Dual Pack"
    next_frames: tuple[str, ...] | None = None  # None when not yet announced


def _parse_dt(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def _clean_item(name: str) -> str:
    """``"M P V Revenant Baruuk Prime Dual Pack"`` -> ``"Revenant Baruuk Prime
    Dual Pack"``. warframestat de-camel-cases the internal ``MPV`` (MegaPrime-
    Vault) prefix into ``"M P V "``; strip it for a clean headline."""
    text = name.strip()
    for prefix in ("M P V ", "MPV "):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    return text.strip()


def _frames_from_pack(featured: str) -> tuple[str, ...]:
    """``"Revenant Baruuk Prime Dual Pack"`` -> ``("Revenant", "Baruuk")``."""
    return tuple(w for w in featured.split() if w.lower() not in _PACK_DESCRIPTORS)


def varzia_rotation(
    raw: dict[str, Any] | None, now: datetime | None = None
) -> VarziaRotation | None:
    """Current + next Varzia rotation, or ``None`` when the payload is missing
    or the current window has already ended (stale)."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(raw, dict):
        return None
    expiry = _parse_dt(raw.get("expiry"))
    if expiry is None or now >= expiry:
        return None

    # Future schedule entries, soonest first: [0] is the current rotation
    # (its expiry is the window end), [1] the next one if announced.
    upcoming: list[tuple[datetime, str]] = []
    for entry in raw.get("schedule") or []:
        if not isinstance(entry, dict):
            continue
        dt = _parse_dt(entry.get("expiry"))
        item = entry.get("item")
        if dt is None or dt <= now or not isinstance(item, str) or not item:
            continue
        upcoming.append((dt, _clean_item(item)))
    upcoming.sort(key=lambda e: e[0])

    current_featured = upcoming[0][1] if upcoming else ""
    next_frames = _frames_from_pack(upcoming[1][1]) if len(upcoming) >= 2 else None
    return VarziaRotation(
        location=str(raw.get("location") or "Maroo's Bazaar (Mars)"),
        expiry=expiry,
        current_frames=_frames_from_pack(current_featured),
        current_featured=current_featured,
        next_frames=next_frames,
    )
