import asyncio
import logging
from dataclasses import dataclass
from importlib import resources
from typing import TYPE_CHECKING, Protocol

import discord
import httpx

if TYPE_CHECKING:
    from titania.bot import TitaniaBot

log = logging.getLogger(__name__)

# WFCD's CDN. It mirrors the WFCD/warframe-items GitHub repo and uses the same
# filenames that the warframestat `/items` endpoint returns in `imageName`. So
# every Warframe icon DE ships in the Public Export is reachable here without
# us packaging anything ourselves.
_CDN_BASE = "https://cdn.warframestat.us/img"

# browse.wf serves DE's text-icon assets directly at their internal Lotus
# paths. The browse.wf "Text Icons" page (browse.wf/text-icons) keys these via
# ExportTextIcons.json — but the actual PNGs live at the path stored in each
# entry's DIT_AUTO field, served as a static asset by browse.wf.
_BROWSE_WF_BASE = "https://browse.wf"


class EmojiSource(Protocol):
    """Resolves an emoji's PNG bytes from somewhere — CDN, bundled asset, etc."""

    async def fetch(self, http: httpx.AsyncClient) -> bytes: ...

    @property
    def origin(self) -> str: ...


@dataclass(frozen=True)
class RemoteSource:
    """Fetches a PNG from cdn.warframestat.us by filename (e.g. 'RelicLithA.png')."""

    filename: str

    @property
    def origin(self) -> str:
        return f"{_CDN_BASE}/{self.filename}"

    async def fetch(self, http: httpx.AsyncClient) -> bytes:
        # cdn.warframestat.us 301-redirects to its underlying object store.
        resp = await http.get(self.origin, follow_redirects=True)
        resp.raise_for_status()
        return resp.content


@dataclass(frozen=True)
class LocalSource:
    """Loads a PNG bundled in titania/assets/. Use for icons WFCD doesn't host
    (e.g. the teal Omnia/Void flame) or operator-supplied custom artwork."""

    filename: str

    @property
    def origin(self) -> str:
        return f"titania/assets/{self.filename}"

    async def fetch(self, _http: httpx.AsyncClient) -> bytes:
        return resources.files("titania.assets").joinpath(self.filename).read_bytes()


# Maps the emoji name (used in `<:name:id>`) to its source. Anything mapped to
# RemoteSource is *not* committed to the repo — it streams from the CDN on
# first startup and lives in Discord's app-emoji storage from then on.
ASSET_TO_EMOJI: dict[str, EmojiSource] = {
    # The "D" variant is the intact/unrefined look; A is the radiant variant
    # in WFCD's naming. We use D so the embed doesn't visually imply every
    # relic is radiant.
    "lith_relic": RemoteSource("RelicLithD.png"),
    "meso_relic": RemoteSource("RelicMesoD.png"),
    "neo_relic": RemoteSource("RelicNeoD.png"),
    "axi_relic": RemoteSource("RelicAxiD.png"),
    "omnia_relic": LocalSource("void.png"),  # no CDN equivalent for Omnia
    "steel_path": RemoteSource("SteelEssence.png"),
    # Currencies. Ducat icon ships on cdn.warframestat.us; the credit icon
    # doesn't, so it's bundled locally as a hand-picked asset.
    "ducats": RemoteSource("Ducat.png"),
    "credits": LocalSource("Credits.png"),
    # Faction/social icons used by the fissure-subscription buttons. Neither
    # is on the warframestat CDN, so the operator drops the PNG into
    # titania/assets/. Missing assets degrade gracefully — sync logs and skips
    # the upload, and the subscription view falls back to a label-only button.
    "tenno": LocalSource("tenno.png"),
    "clan_xp": LocalSource("clan_xp.png"),
}


class EmojiRegistry:
    """Application-level Discord emoji bucket for Titania.

    Lifecycle (idempotent):
      1. On `sync`, list existing application emojis on the bot.
      2. For each desired emoji, reuse the existing one or fetch+upload it.
      3. Cache the `<:name:id>` markup so renderers can drop it inline.

    Discord stores uploaded emojis indefinitely on the application, so the CDN
    is only touched on the very first startup of a new bot account — after
    that, every restart hits Discord's `fetch_application_emojis` and we're
    done. If the CDN happens to be down at first startup, that specific emoji
    falls back to plain text and the rest of the bot keeps working.
    """

    def __init__(self) -> None:
        self._markup: dict[str, str] = {}
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    async def sync(self, bot: "TitaniaBot") -> None:
        try:
            existing = await bot.fetch_application_emojis()
        except discord.HTTPException as e:
            log.warning("could not list application emojis (%s); skipping sync", e)
            return

        by_name = {e.name: e for e in existing}
        async with httpx.AsyncClient(timeout=15.0) as http:
            for name, source in ASSET_TO_EMOJI.items():
                if name in by_name:
                    self._markup[name] = str(by_name[name])
                    continue
                try:
                    data = await source.fetch(http)
                except (httpx.HTTPError, FileNotFoundError) as e:
                    log.warning(
                        "could not fetch emoji %s from %s: %s",
                        name,
                        source.origin,
                        e,
                    )
                    continue
                try:
                    created = await bot.create_application_emoji(name=name, image=data)
                    self._markup[name] = str(created)
                    log.info("uploaded :%s: from %s", name, source.origin)
                except discord.HTTPException as e:
                    log.error("failed to upload emoji %s: %s", name, e)
        self._ready = True

    def get(self, name: str, fallback: str = "") -> str:
        return self._markup.get(name, fallback)


def _normalize_emoji_name(image_name: str) -> str:
    """Discord emoji names must be 2-32 chars and may only contain [a-z0-9_].
    We derive a stable name from the source filename so we can find an
    already-uploaded emoji on later lookups."""
    base = image_name.rsplit(".", 1)[0]
    # Lower + non-alnum → _
    out = "".join(ch.lower() if ch.isalnum() else "_" for ch in base)
    # Collapse repeated underscores and clamp length.
    while "__" in out:
        out = out.replace("__", "_")
    out = out.strip("_") or "item"
    if len(out) > 32:
        # Keep the head; collisions are extremely unlikely with item names.
        out = out[:32].rstrip("_")
    return f"wf_{out}"[:32]


class ItemEmojiCache:
    """Lazily fetches per-Baro-item icons from cdn.warframestat.us and uploads
    them as application emojis on first sight. Subsequent visits reuse the
    Discord-stored emoji indefinitely (Discord *is* the cache; the app-emoji
    bucket has 2000 slots, far more than Baro has ever sold).

    Failures (CDN miss, Discord rate limit, etc.) degrade gracefully — the
    embed falls back to plain text for that one item."""

    def __init__(self) -> None:
        self._markup: dict[str, str] = {}  # image_name -> "<:name:id>"
        self._refreshed_listing = False
        self._lock = asyncio.Lock()

    def get(self, image_name: str) -> str | None:
        return self._markup.get(image_name)

    async def ensure(self, bot: "TitaniaBot", image_name: str) -> str | None:
        """Returns markup for the given imageName, uploading if needed.
        Returns None on any failure (so callers can fall back to text)."""
        if image_name in self._markup:
            return self._markup[image_name]
        async with self._lock:
            if image_name in self._markup:
                return self._markup[image_name]
            # First call ever: refresh the existing-emoji listing so we don't
            # re-upload anything already in the application's emoji bucket.
            if not self._refreshed_listing:
                try:
                    existing = await bot.fetch_application_emojis()
                except discord.HTTPException as e:
                    log.warning("could not list application emojis (%s)", e)
                    return None
                for e in existing:
                    # Match emojis we previously uploaded by inverting our naming.
                    if e.name.startswith("wf_"):
                        # We don't know which image_name produced this — store
                        # under both the name itself and any image we encounter
                        # later that hashes to it.
                        self._markup.setdefault(e.name, str(e))
                self._refreshed_listing = True
            emoji_name = _normalize_emoji_name(image_name)
            if emoji_name in self._markup:
                self._markup[image_name] = self._markup[emoji_name]
                return self._markup[image_name]
            return await self._upload(bot, image_name, emoji_name)

    async def _upload(
        self, bot: "TitaniaBot", image_name: str, emoji_name: str
    ) -> str | None:
        url = f"{_CDN_BASE}/{image_name}"
        async with httpx.AsyncClient(timeout=15.0) as http:
            try:
                resp = await http.get(url, follow_redirects=True)
                resp.raise_for_status()
                data = resp.content
            except httpx.HTTPError as e:
                log.warning("CDN miss for %s: %s", image_name, e)
                return None
        try:
            created = await bot.create_application_emoji(name=emoji_name, image=data)
        except discord.HTTPException as e:
            log.warning("upload failed for %s (%s)", image_name, e)
            return None
        markup = str(created)
        self._markup[image_name] = markup
        self._markup[emoji_name] = markup
        log.info("uploaded :%s: from %s", emoji_name, url)
        return markup
