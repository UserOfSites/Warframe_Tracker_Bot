import logging
from datetime import datetime, timezone

import discord

from titania.data.baro.history import humanize_since
from titania.domain.alerts import AlertEntry
from titania.domain.calendar import CalendarReward
from titania.domain.varzia import VarziaRotation
from titania.domain.baro import BaroBoard, EnrichedBaroItem
from titania.domain.invasions import NotableInvasion
from titania.domain.vendors import (
    ArchonShard,
    ShardOffer,
    TeshinReward,
    current_shiny_treasure_shard,
    current_teshin_reward,
)
from titania.i18n.translator import Translator
from titania.presentation.tables import humanize_remaining
from titania.services.emoji_registry import EmojiRegistry

log = logging.getLogger(__name__)

_FIELD_VALUE_LIMIT = 1024
_INVENTORY_FIELD_NAME = "Inventory"
_INVENTORY_FIELD_CONT = "\u200b"

# Discord embed hard limits used by the compact fallback.
_DESCRIPTION_LIMIT = 4096
_TOTAL_EMBED_LIMIT = 6000

# Above this many items in inventory, switch from the two-column grid to a
# compact "grouped list" description. Normal Baro visits ship 15-20 items;
# TennoCon visits historically ship 50-100+ (returning inventory), which
# blasts through Discord's 25-field / 6000-char embed limits under the grid
# layout. 30 is a comfortable line: it covers TennoCon and any future
# "returning items" event without derailing normal visits.
_COMPACT_MODE_THRESHOLD = 30


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


# --- compact mode (TennoCon Baro et al.) --------------------------------------

# Order + label for the compact-mode category headers. Anything not matched
# falls into ``_OTHER_CATEGORY`` at the bottom. Plain text (no Unicode
# icons) — the renderer bolds the label itself for visual separation.
_CATEGORY_ORDER: tuple[str, ...] = (
    "Weapons",
    "Mods",
    "Relics",
    "Cosmetics",
    "Music",
    "Other",
)
_OTHER_CATEGORY = "Other"

_CATEGORY_PREFIXES: tuple[tuple[str, str], ...] = (
    # Ordered — first match wins.
    ("Weapon",         "Weapons"),
    ("Primed Mod",     "Mods"),
    ("Mod",            "Mods"),
    ("Void Relic",     "Relics"),
    ("Cosmetic",       "Cosmetics"),
    ("Skin",           "Cosmetics"),
    ("Ship Decoration","Cosmetics"),
    ("Glyph",          "Cosmetics"),
    ("Emote",          "Cosmetics"),
    ("Sigil",          "Cosmetics"),
    ("Syandana",       "Cosmetics"),
    ("Somachord",      "Music"),
)


def _categorize(item: EnrichedBaroItem) -> str:
    t = (item.item_type or "").strip()
    if not t:
        return _OTHER_CATEGORY
    for prefix, category in _CATEGORY_PREFIXES:
        if t.startswith(prefix):
            return category
    return _OTHER_CATEGORY


def _days_since(item: EnrichedBaroItem, now: datetime) -> int | None:
    if item.last_appearance is None:
        return None
    return (now.date() - item.last_appearance).days


def _rarity_sort_key(item: EnrichedBaroItem, now: datetime) -> tuple:
    """Rarer returns first: known items with a long gap, then known items with
    a short gap, then never-before-seen at the end."""
    days = _days_since(item, now)
    if days is not None:
        return (0, -days, item.name.lower())
    if item.wiki_known and item.total_appearances >= 1:
        return (1, 0, item.name.lower())  # "first appearance" band
    if item.wiki_known:
        return (2, 0, item.name.lower())  # "always available" band
    return (3, 0, item.name.lower())      # unknown


def _short_days(days: int) -> str:
    if days >= 365:
        y, d = divmod(days, 365)
        return f"{y}y{d}d" if d else f"{y}y"
    if days >= 60:
        mo = days // 30
        return f"{mo}mo"
    return f"{days}d"


def _compact_line(item: EnrichedBaroItem, now: datetime) -> str:
    """Single-line dense format: ``• Name · 525d · 96d ago``.

    Compared to the grid renderer's two-line block, this drops the icon,
    the credit chip (redundant with ducats for buying decisions), and the
    ``|`` separator — the goal is fitting 60-100 items in a single embed
    description without blowing the 4096-char limit."""
    parts = [f"**{item.name}**"]
    if item.ducats:
        parts.append(f"{item.ducats}d")
    days = _days_since(item, now)
    if days is not None:
        parts.append(f"{_short_days(days)} ago")
    elif item.wiki_known and item.total_appearances == 0:
        parts.append("always")
    elif item.wiki_known:
        parts.append("first")
    return "• " + " · ".join(parts)


def _render_compact_body(board: BaroBoard, now: datetime) -> str:
    """Full inventory grouped by category, one line per item, sorted by
    rarity within each category."""
    grouped: dict[str, list[EnrichedBaroItem]] = {c: [] for c in _CATEGORY_ORDER}
    for item in board.enriched_inventory:
        grouped[_categorize(item)].append(item)

    parts: list[str] = [f"**{len(board.enriched_inventory)} items on offer**"]
    for category in _CATEGORY_ORDER:
        bucket = grouped[category]
        if not bucket:
            continue
        bucket.sort(key=lambda it: _rarity_sort_key(it, now))
        parts.append("")  # blank line separator
        parts.append(f"__{category}__ ({len(bucket)})")
        parts.extend(_compact_line(it, now) for it in bucket)
    return "\n".join(parts)


def _truncate_to_fit(header: str, body: str) -> tuple[str, int]:
    """Fit ``header + body`` into Discord's description limit. Returns the
    (possibly-truncated) combined string and the count of dropped lines.
    Truncation is line-aware so we never cut mid-item."""
    combined = f"{header}\n\n{body}"
    if len(combined) <= _DESCRIPTION_LIMIT:
        return combined, 0
    # Trim body lines from the tail until it fits, then append a marker.
    lines = body.split("\n")
    dropped = 0
    footer_reserve = 60  # room for the truncation notice
    while lines and len(f"{header}\n\n" + "\n".join(lines)) + footer_reserve > _DESCRIPTION_LIMIT:
        lines.pop()
        dropped += 1
    body_trimmed = "\n".join(lines)
    notice = f"\n\n_…and {dropped} more item(s) — embed limit reached._"
    return f"{header}\n\n{body_trimmed}{notice}", dropped


def _use_compact_mode(board: BaroBoard) -> bool:
    return len(board.enriched_inventory) > _COMPACT_MODE_THRESHOLD


def build_baro_inventory_embed(
    board: BaroBoard,
    translator: Translator,
    registry: EmojiRegistry,
    item_icons: dict[str, str] | None = None,
) -> discord.Embed:
    """Baro's **full inventory** embed — shown ephemerally when a user clicks
    the inventory link on the summary embed (``/vendors inventory``).

    Inventory renders as a **two-column** grid of ``inline=True`` fields.
    Items with a history chip (weapons, mods, relics) take two lines per
    block; cosmetics take one. If the inventory overflows the per-field
    1024-char cap, we emit multiple (left, right, spacer) triplets — the
    ``"​"`` spacer fills Discord's third inline slot so each row keeps
    rendering as exactly two visible columns instead of three.
    """
    embed = discord.Embed(
        title="Baro Ki'Teer — Inventory",
        color=discord.Color.gold(),
        timestamp=board.generated_at,
    )
    header = _render_baro_header(board, translator)
    embed.description = header
    if board.state.is_present and _use_compact_mode(board):
        # TennoCon-style bulk inventory: the grid renderer would blow past
        # both the 25-field and 6000-char embed caps. Fall back to a dense
        # description-only layout grouped by category.
        body = _render_compact_body(board, datetime.now(timezone.utc))
        combined, dropped = _truncate_to_fit(header, body)
        if dropped:
            log.warning(
                "compact Baro embed truncated: %d of %d items dropped to fit description",
                dropped,
                len(board.enriched_inventory),
            )
        embed.description = combined
        embed.set_footer(text=translator.t("embed.footer.updated"))
        return embed
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


def _render_baro_summary(
    board: BaroBoard,
    inventory_mention: str | None,
    registry: EmojiRegistry,
) -> str:
    """Baro's line(s) on the multi-vendor summary embed.

    - **Absent:** a single line — where he'll appear and (via Discord's native
      relative timestamp) in how long: ``Baro Ki'Teer — Orcus Relay · Arrives
      in 5 days``.
    - **Present:** the relay he's in plus a clickable link that opens the
      ``/vendors inventory`` command, whose reply is an ephemeral (dismissible)
      inventory listing just for the clicking user.

    Baro's marker is his ducat icon (falls back to 🛒 until the emoji uploads).
    """
    marker = registry.get("baro", "🛒")
    state = board.state
    if not state.is_present:
        arrives = f"<t:{int(state.activation.timestamp())}:R>"
        return f"{marker} **Baro Ki'Teer** — {state.location} · Arrives {arrives}"
    leaves = f"<t:{int(state.expiry.timestamp())}:R>"
    link = inventory_mention or "`/vendors inventory`"
    return (
        f"{marker} **Baro Ki'Teer** — here now 📍 {state.location} · Leaves {leaves}\n"
        f"🔎 See his full inventory (only you'll see it): {link}"
    )


# Custom emoji don't render in embed field *names*, so each vendor section is
# built entirely inside the field value: a header line (marker icon + bold
# vendor name) followed by the detail line (item/shard icon + text). The field
# name itself is a zero-width space.
def _render_archon_value(archon: ArchonShard | None, registry: EmojiRegistry) -> str:
    # Narmer crest precedes the "Archon Hunt" header.
    header = f"{registry.get('narmer', '🦉')} **Archon Hunt**"
    if archon is None:
        return f"{header}\n_Unavailable right now._"
    # Real in-game shard icon; the coloured circle is the text fallback when the
    # custom emoji hasn't been uploaded yet (e.g. CDN down on first startup).
    icon = registry.get(archon.icon_key, archon.emoji)
    # Show only the shard on offer — not which Archon awards it.
    return f"{header}\n{icon} {archon.shard_name} ({archon.color})"


def _render_teshin_value(teshin: TeshinReward, registry: EmojiRegistry) -> str:
    # Steel Essence precedes the "Teshin" header.
    header = f"{registry.get('steel_path', '⚔️')} **Teshin** · Steel Path Honors"
    icon = registry.get(teshin.icon_key, teshin.fallback_emoji)
    return f"{header}\n{icon} {teshin.name}"


def _render_shard_offer_value(shard: ShardOffer, registry: EmojiRegistry) -> str:
    # Cavia crest precedes the "Bird 3 (Shiny Treasures)" header.
    header = f"{registry.get('cavia', '✨')} **Bird 3 (Shiny Treasures)**"
    icon = registry.get(shard.icon_key, shard.fallback_emoji)
    return f"{header}\n{icon} {shard.shard_name} ({shard.color})"


def _render_alerts_value(alerts: list[AlertEntry]) -> str:
    """One line per active alert. The caller omits the whole block when there
    are none active."""
    lines = ["🚨 **Alerts**"]
    for a in alerts:
        mt = f" ({a.mission_type})" if a.mission_type else ""
        ts = f"<t:{int(a.expiry.timestamp())}:R>"
        lines.append(f"**{a.reward}** — {a.node}{mt} · ends {ts}")
    return "\n".join(lines)


# Calendar Archon-shard reward name -> the real in-game shard icon key. The
# calendar awards a single shard colour at a time ("Archon Crystal <colour>").
_CALENDAR_SHARD_ICON: dict[str, str] = {
    "boreal": "archon_shard_azure",
    "amar": "archon_shard_crimson",
    "nira": "archon_shard_amber",
}

# Booster reward name -> its icon key. Order matters: the more specific "drop
# chance" phrases must be tested before the plainer "resource" one.
_CALENDAR_BOOSTER_ICON: tuple[tuple[str, str], ...] = (
    ("resource drop chance", "booster_resource_drop_chance"),
    ("mod drop chance", "booster_mod_drop_chance"),
    ("affinity", "booster_affinity"),
    ("credit", "booster_credit"),
    ("resource", "booster_resource"),
)


def _calendar_icon(reward: CalendarReward, registry: EmojiRegistry) -> str:
    lc = reward.reward.lower()
    if reward.kind == "shard":
        for colour, key in _CALENDAR_SHARD_ICON.items():
            if colour in lc:
                return registry.get(key, "🔷")
        return "🔷"
    for needle, key in _CALENDAR_BOOSTER_ICON:
        if needle in lc:
            return registry.get(key, "⏫")
    return "⏫"  # booster of an unrecognised type


def _render_calendar_value(
    rewards: list[CalendarReward], registry: EmojiRegistry
) -> str:
    """One line per notable calendar reward (Archon shards + boosters). The
    caller omits the whole block when the list is empty."""
    lines = [f"{registry.get('calendar', '📅')} **Calendar (1999)**"]
    for r in rewards:
        day = f"{r.day} · " if r.day else ""
        lines.append(f"{_calendar_icon(r, registry)} {day}{r.reward}")
    return "\n".join(lines)


def _render_varzia_value(varzia: VarziaRotation, registry: EmojiRegistry) -> str:
    """Varzia's current Prime Resurgence rotation (frames + time left) and the
    next one — the announced frames, or a countdown when not yet announced. The
    caller omits the block when there's no active rotation."""
    ends = f"<t:{int(varzia.expiry.timestamp())}:R>"
    icon = registry.get("varzia", "🔮")
    lines = [f"{icon} **Varzia aya rotation** · ends {ends}"]
    lines.append(", ".join(varzia.current_frames) if varzia.current_frames
                 else (varzia.current_featured or "_Unknown_"))
    lines.append(f"{icon} **Next Varzia rotation**")
    if varzia.next_frames:
        lines.append(", ".join(varzia.next_frames))
    else:
        # Not announced yet — the next rotation goes live when this one ends.
        lines.append(f"_Not yet announced_ · in {ends}")
    return "\n".join(lines)


def _render_invasions_value(
    invasions: list[NotableInvasion], icons: dict[str, str]
) -> str:
    """One line per notable invasion, each led by its reward's real in-game
    icon (uploaded on demand). The caller omits the block when the list is
    empty."""
    lines = ["⚔️ **Invasions**"]
    for inv in invasions:
        icon = icons.get(inv.image_name or "", "")
        prefix = f"{icon} " if icon else ""
        lines.append(f"{prefix}**{inv.reward}** — {inv.node}")
    return "\n".join(lines)


def build_vendors_embed(
    board: BaroBoard,
    translator: Translator,
    registry: EmojiRegistry,
    *,
    archon: ArchonShard | None = None,
    teshin: TeshinReward | None = None,
    shiny_treasures: ShardOffer | None = None,
    alerts: list[AlertEntry] | None = None,
    invasions: list[NotableInvasion] | None = None,
    invasion_icons: dict[str, str] | None = None,
    calendar: list[CalendarReward] | None = None,
    varzia: VarziaRotation | None = None,
    inventory_mention: str | None = None,
) -> discord.Embed:
    """Multi-vendor **summary** embed — the one posted to tracked channels and
    returned by ``/vendors baro``.

    Rolls up several vendors at a glance:

    - **Varzia (Prime Resurgence)** — shown on top while a rotation is active:
      the current rotation's frames + time left, then the next rotation's frames
      (or a countdown when DE hasn't announced them yet).
    - **Baro Ki'Teer** — arrival countdown when absent; relay + a clickable
      link to the ephemeral inventory when present (the full item grid lives in
      :func:`build_baro_inventory_embed`, not here).
    - **Teshin** — the current static weekly Steel Path Honors reward.
    - **Archon Hunt** — the current Archon (fetched) and the shard it awards.
    - **Bird 3 (Shiny Treasures)** — a separate shard offering (unrelated to the
      Archon Hunt) on its own weekly rotation.
    - **Invasions** — only invasions rewarding a notable item (Orokin Reactor /
      Catalyst, Forma, Exilus Warframe Adapter), each led by that reward's real
      in-game icon; omitted otherwise.
    - **Alerts** — every currently-active alert, appended when any is live and
      omitted entirely otherwise.

    The vendors render as a **vertical list** in the description (one block
    each), not a column grid.

    ``teshin`` / ``shiny_treasures`` default to the current week's rotation
    entry; callers (tests) may inject a specific one for determinism.
    """
    teshin = teshin or current_teshin_reward()
    shiny_treasures = shiny_treasures or current_shiny_treasure_shard()
    embed = discord.Embed(
        title="Vendors",
        color=discord.Color.gold(),
        timestamp=board.generated_at,
    )
    sections: list[str] = []
    # Varzia (Prime Resurgence) sits on top of the weekly vendors while a
    # rotation is active; omitted when the feed is stale/absent.
    if varzia is not None:
        sections.append(_render_varzia_value(varzia, registry))
    sections += [
        _render_baro_summary(board, inventory_mention, registry),
        _render_teshin_value(teshin, registry),
        _render_archon_value(archon, registry),
        _render_shard_offer_value(shiny_treasures, registry),
    ]
    # Calendar (1999) rides along only when the active season awards an Archon
    # shard or a booster; omitted entirely otherwise.
    if calendar:
        sections.append(_render_calendar_value(calendar, registry))
    # Invasions ride along only when a notable reward is up (potato / Forma /
    # Exilus adapter); omitted entirely otherwise.
    if invasions:
        sections.append(_render_invasions_value(invasions, invasion_icons or {}))
    # Alerts ride along whenever any is active; omitted when there are none.
    if alerts:
        sections.append(_render_alerts_value(alerts))
    # Single newline between blocks (not a blank line) keeps the list compact.
    embed.description = "\n\n".join(sections)
    embed.set_footer(text=translator.t("embed.footer.updated"))
    return embed
