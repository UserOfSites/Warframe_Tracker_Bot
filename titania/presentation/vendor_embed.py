from datetime import datetime, timezone

import discord

from titania.data.baro.history import humanize_since
from titania.domain.baro import BaroBoard, EnrichedBaroItem
from titania.i18n.translator import Translator
from titania.presentation.tables import humanize_remaining
from titania.services.emoji_registry import EmojiRegistry

_FIELD_VALUE_LIMIT = 1024
_INVENTORY_FIELD_NAME = "Inventory"
_INVENTORY_FIELD_CONT = "\u200b"


def _short_credits(c: int) -> str:
    """`175000` → `'175k'`, `1500000` → `'1.5M'`."""
    if c >= 1_000_000:
        millions = c / 1_000_000
        return f"{millions:.1f}M".replace(".0M", "M")
    if c >= 1_000:
        return f"{c // 1000}k"
    return str(c)


def _cost_chip(item: EnrichedBaroItem, registry: EmojiRegistry) -> str:
    """Compact `<emoji>525 <emoji>175k` for an inventory item."""
    parts = []
    if item.ducats:
        ducat_emoji = registry.get("ducats", "")
        parts.append(f"{ducat_emoji}{item.ducats}".strip())
    if item.credits:
        credit_emoji = registry.get("credits", "")
        parts.append(f"{credit_emoji}{_short_credits(item.credits)}".strip())
    return " ".join(parts) if parts else "—"


_HISTORY_TYPE_PREFIXES = ("Weapon", "Mod ", "Primed Mod ")
_HISTORY_TYPE_EXACT = frozenset({"Void Relic"})


def _shows_history(item: EnrichedBaroItem) -> bool:
    """Whether the last-appearance chip is worth rendering for this item.

    Weapons, mods (regular + primed, any slot), and relics warrant it because
    a Baro shopper's buying decision depends on how long until the next visit.
    Cosmetics, decorations, glyphs and the like get a name+cost line only.
    """
    t = (item.item_type or "").strip()
    if not t:
        return False
    if t in _HISTORY_TYPE_EXACT:
        return True
    return any(t.startswith(p) for p in _HISTORY_TYPE_PREFIXES)


def _when_chip(item: EnrichedBaroItem, now: datetime) -> str:
    """Last-seen chip, with four distinct states:

    - dated history → ``humanize_since(last_appearance)``;
    - wiki entry exists but the date log is empty → ``"always"``
      (wiki convention for staples like Sands of Inaros Blueprint or
      Fae Path Ephemera that appear every visit);
    - wiki entry exists with only the current visit recorded → ``"first appearance"``;
    - no wiki entry at all → ``"unknown"`` (novel item or upstream name we
      couldn't reconcile).
    """
    if item.last_appearance is not None:
        return humanize_since(item.last_appearance, now)
    if item.wiki_known and item.total_appearances == 0:
        return "always"
    if item.total_appearances >= 1:
        return "first appearance"
    return "unknown"


def _render_baro_header(
    board: BaroBoard,
    translator: Translator,
) -> str:
    # Native Discord relative timestamps so the countdown stays readable on
    # mobile (the backtick form rendered white-on-white in the official app)
    # and updates client-side without us editing the message.
    state = board.state
    if not state.is_present:
        arrives = f"<t:{int(state.activation.timestamp())}:R>"
        return (
            f"**{state.character}**\n"
            f"📍 {state.location}\n"
            f"⏳ Arrives {arrives}"
        )
    leaves = f"<t:{int(state.expiry.timestamp())}:R>"
    return (
        f"**{state.character}** — here now\n"
        f"📍 {state.location}  ·  Leaves {leaves}"
    )


def _render_inventory_lines(
    board: BaroBoard,
    registry: EmojiRegistry,
    item_icons: dict[str, str],
) -> list[str]:
    """One compact line per item, suitable for a multi-column grid layout.

    Weapons, mods, and relics carry a "last seen X ago" chip — the rotation
    history is what shoppers actually care about for those. Cosmetics and
    decorations get a clean name+cost line, since "first appearance" /
    "unknown" labels on novelty items are noise.
    """
    now = datetime.now(timezone.utc)
    lines: list[str] = []
    for item in board.enriched_inventory:
        icon = item_icons.get(item.image_name or "", "")
        prefix = f"{icon} " if icon else "• "
        cost = _cost_chip(item, registry)
        if _shows_history(item):
            when = _when_chip(item, now)
            lines.append(f"{prefix}**{item.name}** {cost} · {when}")
        else:
            lines.append(f"{prefix}**{item.name}** {cost}")
    return lines


def _chunk_into_fields(lines: list[str], limit: int) -> list[str]:
    """Pack item lines into field values ≤ `limit` chars, joined by newline."""
    fields: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        added = len(line) + (1 if current else 0)
        if current and current_len + added > limit:
            fields.append("\n".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += added
    if current:
        fields.append("\n".join(current))
    return fields


def build_vendors_embed(
    board: BaroBoard,
    translator: Translator,
    registry: EmojiRegistry,
    item_icons: dict[str, str] | None = None,
) -> discord.Embed:
    """Currently single-vendor (Baro). Designed for new sections (Teshin,
    Varzia, …) to be appended as the project grows, all in one embed.

    Inventory renders as a multi-column grid: items packed into
    ``inline=True`` fields, which Discord lays out side-by-side (~3 per row
    on desktop). ``item_icons`` is a snapshot of {image_name: discord_emoji_markup}
    produced by the dynamic per-item uploader; missing entries render with a
    bullet prefix instead.
    """
    embed = discord.Embed(
        title="Vendors",
        color=discord.Color.gold(),
        timestamp=board.generated_at,
    )
    embed.description = _render_baro_header(board, translator)
    if board.state.is_present:
        lines = _render_inventory_lines(board, registry, item_icons or {})
        for i, value in enumerate(
            _chunk_into_fields(lines, _FIELD_VALUE_LIMIT)
        ):
            embed.add_field(
                name=_INVENTORY_FIELD_NAME if i == 0 else _INVENTORY_FIELD_CONT,
                value=value,
                inline=False,
            )
    embed.set_footer(text=translator.t("embed.footer.updated"))
    return embed
