from datetime import datetime

import discord

from titania.domain.era import Era
from titania.domain.fissure import Fissure, FissureBoard, NextReset
from titania.i18n.translator import Translator
from titania.presentation.tables import humanize_remaining
from titania.services.emoji_registry import EmojiRegistry

ERA_EMOJI_KEY: dict[Era, str] = {
    Era.LITH: "lith_relic",
    Era.MESO: "meso_relic",
    Era.NEO: "neo_relic",
    Era.AXI: "axi_relic",
    Era.OMNIA: "omnia_relic",
    # Requiem is filtered upstream and has no asset.
}

# Column gutter for rows in the description. Discord renders proportional font
# there, so regular spaces collapse; em-spaces (U+2003) survive and give the
# row its visual "columns". Two em-spaces ≈ a tab-stop in most clients.
_COL_GAP = "  "


def _era_marker(era: Era, is_sp: bool, registry: EmojiRegistry) -> str:
    era_emoji = registry.get(ERA_EMOJI_KEY.get(era, ""), era.value)
    if not is_sp:
        return era_emoji
    sp_emoji = registry.get("steel_path", "[SP] ")
    return f"{sp_emoji}{era_emoji}"


def _quality_marker(
    node: str,
    excellent_nodes: frozenset[str],
    good_nodes: frozenset[str],
) -> str:
    """Per-guild "quality" prefix for a fissure row.

    🌟 outranks ⭐ if a node is in both sets (settings panel keeps them
    mutually exclusive, but rendering is defensive). Empty string when the
    node carries no marker — most nodes won't.
    """
    node_lc = node.strip().lower()
    if any(n.lower() == node_lc for n in excellent_nodes):
        return "🌟 "
    if any(n.lower() == node_lc for n in good_nodes):
        return "⭐ "
    return ""


def _render_fissure_row(
    f: Fissure,
    now: datetime,
    translator: Translator,
    registry: EmojiRegistry,
    *,
    excellent_nodes: frozenset[str] = frozenset(),
    good_nodes: frozenset[str] = frozenset(),
) -> str:
    marker = _era_marker(f.era, f.is_steel_path, registry)
    quality = _quality_marker(f.node, excellent_nodes, good_nodes)
    location = f"{f.node} ({f.planet})" if f.planet else f.node
    eta = humanize_remaining(f.expires_at - now, translator)
    return (
        f"{quality}{marker} **{f.era.value}**{_COL_GAP}"
        f"{f.mission_type.value} — {location}{_COL_GAP}"
        f"`{eta}`"
    )


def _render_section(
    title: str,
    fissures: list[Fissure],
    now: datetime,
    translator: Translator,
    registry: EmojiRegistry,
    empty_hint: str,
    *,
    excellent_nodes: frozenset[str] = frozenset(),
    good_nodes: frozenset[str] = frozenset(),
) -> str:
    if not fissures:
        return f"**{title}**\n_{empty_hint}_"
    lines = [f"**{title}**"]
    lines.extend(
        _render_fissure_row(
            f, now, translator, registry,
            excellent_nodes=excellent_nodes, good_nodes=good_nodes,
        )
        for f in fissures
    )
    return "\n".join(lines)


def _render_resets_block(
    resets: list[NextReset],
    now: datetime,
    translator: Translator,
    registry: EmojiRegistry,
) -> str:
    if not resets:
        return f"_{translator.t('embed.next_resets_block.none_active')}_"
    lines = []
    for r in resets:
        marker = _era_marker(r.era, False, registry)
        eta = humanize_remaining(r.expires_at - now, translator)
        lines.append(f"{marker} **{r.era.value}**{_COL_GAP}`{eta}`")
    return "\n".join(lines)


def build_fissure_embed(
    board: FissureBoard,
    translator: Translator,
    registry: EmojiRegistry,
    *,
    excellent_nodes: frozenset[str] = frozenset(),
    good_nodes: frozenset[str] = frozenset(),
) -> discord.Embed:
    embed = discord.Embed(
        title=translator.t("embed.title"),
        color=discord.Color.purple(),
        timestamp=board.generated_at,
    )

    sections = [
        _render_section(
            translator.t("embed.section.normal"),
            board.normal,
            board.generated_at,
            translator,
            registry,
            translator.t("embed.empty.normal"),
            excellent_nodes=excellent_nodes,
            good_nodes=good_nodes,
        ),
        _render_section(
            translator.t("embed.section.steel_path"),
            board.steel_path,
            board.generated_at,
            translator,
            registry,
            translator.t("embed.empty.steel_path"),
            excellent_nodes=excellent_nodes,
            good_nodes=good_nodes,
        ),
        _render_section(
            translator.t("embed.section.dojoshare"),
            board.dojoshare,
            board.generated_at,
            translator,
            registry,
            translator.t("embed.empty.dojoshare"),
            excellent_nodes=excellent_nodes,
            good_nodes=good_nodes,
        ),
    ]
    embed.description = "\n\n".join(sections)

    # Next Resets as two inline fields side-by-side.
    normal_resets = [r for r in board.next_resets if not r.is_steel_path]
    sp_resets = [r for r in board.next_resets if r.is_steel_path]
    next_label = translator.t("embed.section.next_resets")
    sp_marker = registry.get("steel_path", "")

    embed.add_field(
        name=f"{next_label} — {translator.t('embed.section.normal')}",
        value=_render_resets_block(normal_resets, board.generated_at, translator, registry),
        inline=True,
    )
    embed.add_field(
        name=(
            f"{next_label} — {sp_marker}{translator.t('embed.section.steel_path')}"
            if sp_marker
            else f"{next_label} — {translator.t('embed.section.steel_path')}"
        ),
        value=_render_resets_block(sp_resets, board.generated_at, translator, registry),
        inline=True,
    )

    embed.set_footer(text=translator.t("embed.footer.updated"))
    return embed
