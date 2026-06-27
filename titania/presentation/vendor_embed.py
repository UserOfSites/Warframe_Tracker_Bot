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
    """Compact ``<emoji>525 | <emoji>175k`` for an inventory item.

    The pipe-separator matches the requested two-column row layout where
    rows look like ``Ducats | Credits | Last seen``.
    """
    parts = []
    if item.ducats:
        ducat_emoji = registry.get("ducats", "")
        parts.append(f"{ducat_emoji}{item.ducats}".strip())
    if item.credits:
        credit_emoji = registry.get("credits", "")
        parts.append(f"{credit_emoji}{_short_credits(item.credits)}".strip())
    return " | ".join(parts) if parts else "—"


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


def _render_inventory_blocks(
    board: BaroBoard,
    registry: EmojiRegistry,
    item_icons: dict[str, str],
) -> list[str]:
    """Per-item blocks for the two-column layout — **two lines per item**:
    ``{icon} **Name**`` on top, then ``ducats | credits`` (with ``| last
    seen`` appended for weapons / mods / relics). All items use the same
    two-line shape so Discord can't word-wrap the stats line at an awkward
    spot — the column width changes how each line *fits*, but the line break
    between name and stats is hard-coded.

    Each block is one element in the returned list — the chunker treats them
    atomically so a block never gets split across two columns.
    """
    now = datetime.now(timezone.utc)
    blocks: list[str] = []
    for item in board.enriched_inventory:
        icon = item_icons.get(item.image_name or "", "")
        prefix = f"{icon} " if icon else "• "
        cost = _cost_chip(item, registry)
        if _shows_history(item):
            when = _when_chip(item, now)
            stats = f"{cost} | {when}"
        else:
            stats = cost
        blocks.append(f"{prefix}**{item.name}**\n{stats}")
    return blocks


def _split_blocks_for_two_columns(
    blocks: list[str],
) -> tuple[list[str], list[str]]:
    """Distribute blocks into left/right columns balanced by character count.
    Goes block-by-block in order, filling the left column until it's at
    least half the total, then dropping the rest into the right column."""
    total = sum(len(b) for b in blocks) + max(len(blocks) - 1, 0)
    target = total // 2
    left: list[str] = []
    right: list[str] = []
    running = 0
    for block in blocks:
        if running < target:
            left.append(block)
            running += len(block) + 1  # +1 for the join newline
        else:
            right.append(block)
    return left, right


def _chunk_into_fields(blocks: list[str], limit: int) -> list[str]:
    """Pack blocks into field values ≤ ``limit`` chars, joined by newline.
    Each block is atomic — never split across chunks."""
    fields: list[str] = []
    current: list[str] = []
    current_len = 0
    for block in blocks:
        added = len(block) + (1 if current else 0)
        if current and current_len + added > limit:
            fields.append("\n".join(current))
            current = [block]
            current_len = len(block)
        else:
            current.append(block)
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

    Inventory renders as a **two-column** grid of ``inline=True`` fields.
    Items with a history chip (weapons, mods, relics) take two lines per
    block; cosmetics take one. If the inventory overflows the per-field
    1024-char cap, we emit multiple (left, right, spacer) triplets — the
    ``"​"`` spacer fills Discord's third inline slot so each row keeps
    rendering as exactly two visible columns instead of three.
    """
    embed = discord.Embed(
        title="Vendors",
        color=discord.Color.gold(),
        timestamp=board.generated_at,
    )
    embed.description = _render_baro_header(board, translator)
    if board.state.is_present:
        blocks = _render_inventory_blocks(board, registry, item_icons or {})
        left_blocks, right_blocks = _split_blocks_for_two_columns(blocks)
        left_chunks = _chunk_into_fields(left_blocks, _FIELD_VALUE_LIMIT)
        right_chunks = _chunk_into_fields(right_blocks, _FIELD_VALUE_LIMIT)
        n_rows = max(len(left_chunks), len(right_chunks))
        needs_spacer = n_rows > 1
        for i in range(n_rows):
            left_value = left_chunks[i] if i < len(left_chunks) else _INVENTORY_FIELD_CONT
            right_value = right_chunks[i] if i < len(right_chunks) else _INVENTORY_FIELD_CONT
            embed.add_field(
                name=_INVENTORY_FIELD_NAME if i == 0 else _INVENTORY_FIELD_CONT,
                value=left_value,
                inline=True,
            )
            embed.add_field(
                name=_INVENTORY_FIELD_CONT,
                value=right_value,
                inline=True,
            )
            if needs_spacer:
                # Force the row to consume all 3 inline slots so Discord
                # doesn't pack a fourth field into the same row.
                embed.add_field(
                    name=_INVENTORY_FIELD_CONT,
                    value=_INVENTORY_FIELD_CONT,
                    inline=True,
                )
    embed.set_footer(text=translator.t("embed.footer.updated"))
    return embed
