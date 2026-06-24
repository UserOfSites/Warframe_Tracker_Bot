from datetime import datetime, timezone

import discord

from titania.data.baro.history import humanize_since
from titania.domain.baro import BaroBoard, EnrichedBaroItem
from titania.i18n.translator import Translator
from titania.presentation.tables import humanize_remaining
from titania.services.emoji_registry import EmojiRegistry


def _cost_chip(
    item: EnrichedBaroItem, registry: EmojiRegistry
) -> str:
    """Compact `<emoji> 525  <emoji> 175,000` for an inventory item."""
    parts = []
    if item.ducats:
        ducat_emoji = registry.get("ducats", "")
        parts.append(f"{ducat_emoji} {item.ducats}".strip())
    if item.credits:
        credit_emoji = registry.get("credits", "")
        parts.append(f"{credit_emoji} {item.credits:,}".strip())
    return "  ".join(parts) if parts else "—"


def _render_baro_section(
    board: BaroBoard,
    translator: Translator,
    registry: EmojiRegistry,
    item_icons: dict[str, str],
) -> str:
    state = board.state
    now = datetime.now(timezone.utc)

    if not state.is_present:
        eta = humanize_remaining(state.activation - now, translator)
        return (
            f"**{state.character}**\n"
            f"📍 {state.location}\n"
            f"⏳ Arrives `{eta}`"
        )

    leaves_in = humanize_remaining(state.expiry - now, translator)
    lines = [
        f"**{state.character}** — here now",
        f"📍 {state.location}  ·  Leaves `{leaves_in}`",
        "",
    ]
    for item in board.enriched_inventory:
        last_seen = (
            humanize_since(item.last_appearance, now)
            if item.last_appearance is not None
            else "first appearance"
        )
        icon = item_icons.get(item.image_name or "", "")
        prefix = f"{icon} " if icon else "• "
        cost = _cost_chip(item, registry)
        # Two lines per item: header with name + icon, indented price + history.
        lines.append(f"{prefix}**{item.name}**")
        lines.append(f"   {cost}  ·  last seen {last_seen}")
    return "\n".join(lines)


def build_vendors_embed(
    board: BaroBoard,
    translator: Translator,
    registry: EmojiRegistry,
    item_icons: dict[str, str] | None = None,
) -> discord.Embed:
    """Currently single-vendor (Baro). Designed for new sections (Teshin,
    Varzia, …) to be appended as the project grows, all in one embed.

    ``item_icons`` is a snapshot of {image_name: discord_emoji_markup} produced
    by the dynamic per-item uploader. Empty/missing entries render with a
    bullet prefix instead.
    """
    embed = discord.Embed(
        title="Vendors",
        color=discord.Color.gold(),
        timestamp=board.generated_at,
    )
    embed.description = _render_baro_section(
        board, translator, registry, item_icons or {}
    )
    embed.set_footer(text=translator.t("embed.footer.updated"))
    return embed
