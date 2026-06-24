from pathlib import Path

import pytest

from titania.config import Config
from titania.storage.db import Database
from titania.storage.tracked_channels_repo import (
    TrackedChannel,
    TrackedChannelsRepository,
)


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(  # type: ignore[call-arg]
        DISCORD_TOKEN="dummy",
        DB_PATH=str(tmp_path / "test.db"),
    )


@pytest.fixture
async def repo(cfg: Config):
    db = Database(cfg.db_path)
    await db.connect()
    try:
        yield TrackedChannelsRepository(db)
    finally:
        await db.close()


async def test_get_returns_none_when_no_tracking(repo: TrackedChannelsRepository):
    assert await repo.get(1) is None


async def test_upsert_then_get_round_trips(repo: TrackedChannelsRepository):
    tc = TrackedChannel(guild_id=42, channel_id=100, message_id=999)
    await repo.upsert(tc)
    assert await repo.get(42) == tc


async def test_upsert_replaces_existing_for_same_guild(repo: TrackedChannelsRepository):
    await repo.upsert(TrackedChannel(1, 100, 200))
    await repo.upsert(TrackedChannel(1, 300, 400))
    loaded = await repo.get(1)
    assert loaded == TrackedChannel(1, 300, 400)


async def test_delete_removes_entry(repo: TrackedChannelsRepository):
    await repo.upsert(TrackedChannel(1, 100, 200))
    await repo.delete(1)
    assert await repo.get(1) is None


async def test_list_all_returns_every_tracking_row(repo: TrackedChannelsRepository):
    rows = [
        TrackedChannel(1, 100, 200),
        TrackedChannel(2, 300, 400),
        TrackedChannel(3, 500, 600),
    ]
    for r in rows:
        await repo.upsert(r)
    fetched = sorted(await repo.list_all(), key=lambda t: t.guild_id)
    assert fetched == rows
