import httpx
import pytest
import respx

from titania.services.emoji_registry import (
    ASSET_TO_EMOJI,
    LocalSource,
    RemoteSource,
)


def test_relic_icons_use_remote_cdn_sources():
    # The relic + steel-path icons all come from cdn.warframestat.us so the
    # repo doesn't carry them.
    for key in ("lith_relic", "meso_relic", "neo_relic", "axi_relic", "steel_path"):
        source = ASSET_TO_EMOJI[key]
        assert isinstance(source, RemoteSource), f"{key} should be RemoteSource"
        assert source.origin.startswith("https://cdn.warframestat.us/img/")


def test_omnia_kept_local_because_no_cdn_equivalent():
    # WFCD doesn't ship an Omnia icon — Omnia is keyed off the teal void flame
    # the user supplied; that one stays in titania/assets/.
    source = ASSET_TO_EMOJI["omnia_relic"]
    assert isinstance(source, LocalSource)
    assert source.filename == "void.png"


async def test_local_source_reads_from_package_data():
    src = LocalSource("void.png")
    async with httpx.AsyncClient() as http:
        data = await src.fetch(http)
    # void.png is a small PNG; just confirm it's a non-trivial PNG payload.
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(data) > 0


async def test_remote_source_fetches_from_url():
    with respx.mock(base_url="https://cdn.warframestat.us") as mock:
        mock.get("/img/RelicLithA.png").mock(
            return_value=httpx.Response(200, content=b"\x89PNG\r\n\x1a\nfake-payload")
        )
        async with httpx.AsyncClient() as http:
            src = RemoteSource("RelicLithA.png")
            data = await src.fetch(http)
    assert data.startswith(b"\x89PNG")
    assert b"fake-payload" in data


def test_item_emoji_cache_constructs_cleanly():
    """Smoke test: instantiation must not raise (catches missing imports
    that the heavier integration tests would otherwise miss)."""
    from titania.services.emoji_registry import ItemEmojiCache

    cache = ItemEmojiCache()
    assert cache.get("Anything.png") is None


def test_emoji_registry_constructs_cleanly():
    from titania.services.emoji_registry import EmojiRegistry

    reg = EmojiRegistry()
    assert reg.get("lith_relic") == ""  # empty default before any sync


async def test_remote_source_raises_on_404():
    with respx.mock(base_url="https://cdn.warframestat.us") as mock:
        mock.get("/img/Nonexistent.png").mock(return_value=httpx.Response(404))
        async with httpx.AsyncClient() as http:
            src = RemoteSource("Nonexistent.png")
            with pytest.raises(httpx.HTTPStatusError):
                await src.fetch(http)
