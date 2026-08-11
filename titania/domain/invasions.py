"""Notable-only invasion filtering.

Invasions run constantly and mostly pay out the "usual" build materials
(Fieldron / Detonite Injector / Mutagen Mass) or Nav Coordinates. We surface an
invasion in the vendors embed **only** when one of its two sides rewards
something worth the grind: Forma, an Orokin Reactor/Catalyst ("potato"), or an
Exilus Warframe Adapter. The reward's own CDN thumbnail is carried through so
the embed can show its real in-game icon.
"""

from dataclasses import dataclass
from typing import Any

# Reward-name substrings (lowercased) considered notable. Substring match so
# blueprints count too ("Orokin Reactor Blueprint" → "orokin reactor").
_NOTABLE_SUBSTRINGS: tuple[str, ...] = (
    "forma",
    "orokin reactor",
    "orokin catalyst",
    "exilus warframe adapter",
    "exilus adapter",
)


@dataclass(frozen=True)
class NotableInvasion:
    reward: str  # display reward, e.g. "Orokin Catalyst Blueprint"
    node: str  # "Rusalka (Sedna)"
    image_name: str | None  # CDN filename for the reward icon (from its thumbnail)


def _is_notable(name: str) -> bool:
    lc = name.lower()
    return any(s in lc for s in _NOTABLE_SUBSTRINGS)


def image_name_from_thumbnail(url: Any) -> str | None:
    """``'https://cdn.warframestat.us/img/orokin-reactor.png'`` → ``'orokin-reactor.png'``.

    The item-emoji cache fetches by this filename off the same CDN, so we can
    upload the real reward icon on demand."""
    if not isinstance(url, str) or not url:
        return None
    segment = url.rstrip("/").rsplit("/", 1)[-1]
    return segment or None


def _reward_names(reward: dict[str, Any]) -> list[str]:
    names: list[str] = [str(n) for n in (reward.get("items") or []) if n]
    for ci in reward.get("countedItems") or []:
        if not isinstance(ci, dict):
            continue
        item_type = ci.get("type")
        if not item_type:
            continue
        count = ci.get("count") or 1
        names.append(
            f"{count}x {item_type}" if isinstance(count, int) and count > 1 else str(item_type)
        )
    return names


def notable_invasions(raw: list[dict[str, Any]] | None) -> list[NotableInvasion]:
    """Filter a raw warframestat ``/invasions`` payload to still-running
    invasions whose attacker or defender side rewards a notable item. One entry
    per notable side (an invasion could, rarely, be notable on both)."""
    out: list[NotableInvasion] = []
    for inv in raw or []:
        if not isinstance(inv, dict) or inv.get("completed"):
            continue
        node = str(inv.get("node") or "?")
        for side in ("attacker", "defender"):
            reward = (inv.get(side) or {}).get("reward") or {}
            notable = [n for n in _reward_names(reward) if _is_notable(n)]
            if not notable:
                continue
            out.append(
                NotableInvasion(
                    reward=", ".join(notable),
                    node=node,
                    image_name=image_name_from_thumbnail(reward.get("thumbnail")),
                )
            )
    return out
