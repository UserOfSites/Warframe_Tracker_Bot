from pathlib import Path

import pytest

from titania.config import Config
from titania.storage.db import Database
from titania.storage.user_preferences_repo import UserPreferencesRepository


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
        yield UserPreferencesRepository(db)
    finally:
        await db.close()


async def test_unknown_user_has_not_been_welcomed(repo: UserPreferencesRepository):
    assert (await repo.has_been_welcomed(42)) is False


async def test_mark_welcomed_persists(repo: UserPreferencesRepository):
    await repo.mark_welcomed(42)
    assert (await repo.has_been_welcomed(42)) is True


async def test_mark_welcomed_is_idempotent(repo: UserPreferencesRepository):
    """Two calls in a row shouldn't clobber the original timestamp — we want
    to know when we *first* welcomed the user, not the most recent call."""
    await repo.mark_welcomed(42)
    await repo.mark_welcomed(42)
    assert (await repo.has_been_welcomed(42)) is True


async def test_clear_welcomed_flips_back(repo: UserPreferencesRepository):
    await repo.mark_welcomed(42)
    await repo.clear_welcomed(42)
    assert (await repo.has_been_welcomed(42)) is False


async def test_welcome_flag_independent_of_locale_and_mute(
    repo: UserPreferencesRepository,
):
    """Setting locale or mute must not touch the welcome flag, and vice versa.
    All three axes on the same row need to be updated independently."""
    await repo.set_locale(42, "it")
    await repo.mark_welcomed(42)
    await repo.set_muted(42, True)
    assert (await repo.get_locale(42)) == "it"
    assert (await repo.is_muted(42)) is True
    assert (await repo.has_been_welcomed(42)) is True
    # Now clear only the welcome flag — locale and mute survive.
    await repo.clear_welcomed(42)
    assert (await repo.has_been_welcomed(42)) is False
    assert (await repo.get_locale(42)) == "it"
    assert (await repo.is_muted(42)) is True


async def test_each_user_independent(repo: UserPreferencesRepository):
    await repo.mark_welcomed(1)
    assert (await repo.has_been_welcomed(1)) is True
    assert (await repo.has_been_welcomed(2)) is False
