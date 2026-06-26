import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiosqlite

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id              INTEGER PRIMARY KEY,
    locale                TEXT    NOT NULL DEFAULT 'en',
    allowed_mission_types TEXT    NOT NULL DEFAULT 'Exterminate,Sabotage,Capture,Rescue',
    blocked_nodes         TEXT    NOT NULL DEFAULT '',
    pinned_nodes          TEXT    NOT NULL DEFAULT '',
    dojoshare_nodes       TEXT    NOT NULL DEFAULT 'Draco,Casta,Nimus,Mot,Ani,Elara,Io,Stephano,Circulus,Yuvarium',
    updated_at            TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tracked_channels (
    guild_id   INTEGER PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tracked_vendors_channels (
    guild_id   INTEGER PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fissure_subscriptions (
    guild_id        INTEGER NOT NULL,
    user_id         INTEGER NOT NULL,
    topic           TEXT    NOT NULL,
    nodes_filter    TEXT    NOT NULL DEFAULT '',
    planets_filter  TEXT    NOT NULL DEFAULT '',
    missions_filter TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (guild_id, user_id, topic)
);

CREATE INDEX IF NOT EXISTS idx_fissure_subs_guild_topic
    ON fissure_subscriptions (guild_id, topic);
"""


class Database:
    """Thin wrapper around aiosqlite connection: WAL mode + schema bootstrap."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self._conn is not None:
            return
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(SCHEMA)
        await self._run_migrations()
        await self._conn.commit()
        log.info("database ready at %s", self._path)

    async def _run_migrations(self) -> None:
        """Add columns that newer code expects but older DBs don't have.
        SQLite doesn't support `ADD COLUMN IF NOT EXISTS`, so we introspect."""
        assert self._conn is not None
        async with self._conn.execute("PRAGMA table_info(guild_settings)") as cur:
            cols = {row[1] async for row in cur}
        if "pinned_nodes" not in cols:
            await self._conn.execute(
                "ALTER TABLE guild_settings ADD COLUMN "
                "pinned_nodes TEXT NOT NULL DEFAULT ''"
            )
            log.info("migration: added guild_settings.pinned_nodes")
        async with self._conn.execute(
            "PRAGMA table_info(fissure_subscriptions)"
        ) as cur:
            sub_cols = {row[1] async for row in cur}
        for new_col in ("nodes_filter", "planets_filter", "missions_filter"):
            if new_col not in sub_cols:
                await self._conn.execute(
                    f"ALTER TABLE fissure_subscriptions ADD COLUMN "
                    f"{new_col} TEXT NOT NULL DEFAULT ''"
                )
                log.info("migration: added fissure_subscriptions.%s", new_col)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @asynccontextmanager
    async def cursor(self) -> AsyncIterator[aiosqlite.Cursor]:
        if self._conn is None:
            raise RuntimeError("database not connected; call connect() first")
        async with self._conn.cursor() as cur:
            yield cur

    async def commit(self) -> None:
        if self._conn is not None:
            await self._conn.commit()
