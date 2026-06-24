from pathlib import Path

import pytest

from titania.config import Config
from titania.domain.mission_type import MissionType
from titania.services.guild_settings import GuildSettings
from titania.storage.db import Database
from titania.storage.guild_settings_repo import GuildSettingsRepository


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
        yield GuildSettingsRepository(db, cfg)
    finally:
        await db.close()


async def test_get_returns_default_for_unknown_guild(repo: GuildSettingsRepository):
    settings = await repo.get(12345)
    assert settings == repo.default


async def test_get_returns_default_for_none_guild_id(repo: GuildSettingsRepository):
    settings = await repo.get(None)
    assert settings == repo.default


async def test_save_then_get_round_trips(repo: GuildSettingsRepository):
    custom = GuildSettings(
        allowed_mission_types=frozenset({MissionType.EXTERMINATE, MissionType.SABOTAGE}),
        blocked_nodes=frozenset({"Hepit", "Acheron"}),
        pinned_nodes=frozenset({"Hieracon"}),
        dojoshare_nodes=frozenset({"Mot", "Draco"}),
        locale="it",
    )
    await repo.save(42, custom)
    loaded = await repo.get(42)
    assert loaded == custom


async def test_save_is_idempotent_and_updates(repo: GuildSettingsRepository):
    s1 = GuildSettings(
        allowed_mission_types=frozenset({MissionType.CAPTURE}),
        blocked_nodes=frozenset(),
        pinned_nodes=frozenset(),
        dojoshare_nodes=frozenset({"Mot"}),
        locale="en",
    )
    s2 = GuildSettings(
        allowed_mission_types=frozenset({MissionType.SABOTAGE}),
        blocked_nodes=frozenset({"Hepit"}),
        pinned_nodes=frozenset({"Hieracon"}),
        dojoshare_nodes=frozenset({"Draco"}),
        locale="it",
    )
    await repo.save(99, s1)
    await repo.save(99, s2)
    loaded = await repo.get(99)
    assert loaded == s2


async def test_each_guild_keeps_its_own_settings(repo: GuildSettingsRepository):
    a = GuildSettings(
        allowed_mission_types=frozenset({MissionType.CAPTURE}),
        blocked_nodes=frozenset({"Hepit"}),
        pinned_nodes=frozenset({"Adaro"}),
        dojoshare_nodes=frozenset({"Mot"}),
        locale="en",
    )
    b = GuildSettings(
        allowed_mission_types=frozenset({MissionType.SABOTAGE}),
        blocked_nodes=frozenset({"Ukko"}),
        pinned_nodes=frozenset(),
        dojoshare_nodes=frozenset({"Draco"}),
        locale="it",
    )
    await repo.save(1, a)
    await repo.save(2, b)
    assert await repo.get(1) == a
    assert await repo.get(2) == b
