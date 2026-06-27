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
    excellent_nodes       TEXT    NOT NULL DEFAULT '',
    good_nodes            TEXT    NOT NULL DEFAULT '',
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
    user_id         INTEGER NOT NULL,
    topic           TEXT    NOT NULL,
    -- `subscribed` separates intent from filter state: a row can exist with
    -- subscribed=0 if the user pre-configured a filter via the panel without
    -- having reacted on a tracker. Reactions toggle subscribed; the panel
    -- only touches the filter columns.
    subscribed      INTEGER NOT NULL DEFAULT 1,
    nodes_filter    TEXT    NOT NULL DEFAULT '',
    planets_filter  TEXT    NOT NULL DEFAULT '',
    missions_filter TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, topic)
);

CREATE INDEX IF NOT EXISTS idx_fissure_subs_topic
    ON fissure_subscriptions (topic);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id    INTEGER PRIMARY KEY,
    locale     TEXT    NOT NULL DEFAULT 'en',
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
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
        for star_col in ("excellent_nodes", "good_nodes"):
            if star_col not in cols:
                await self._conn.execute(
                    f"ALTER TABLE guild_settings ADD COLUMN "
                    f"{star_col} TEXT NOT NULL DEFAULT ''"
                )
                log.info("migration: added guild_settings.%s", star_col)
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
        if "subscribed" not in sub_cols:
            # Existing rows pre-date the panel/filter separation — they were
            # all created by reactions, so they're already subscribed.
            await self._conn.execute(
                "ALTER TABLE fissure_subscriptions ADD COLUMN "
                "subscribed INTEGER NOT NULL DEFAULT 1"
            )
            log.info("migration: added fissure_subscriptions.subscribed")
        if "guild_id" in sub_cols:
            # Drop the guild_id dimension — subscriptions are now global per
            # user. Rebuild the table, deduping by (user_id, topic) and OR-
            # merging filter columns so a user with rows in multiple guilds
            # keeps a sensible composite filter rather than losing all but one.
            log.info("migration: rebuilding fissure_subscriptions without guild_id")
            await self._conn.executescript(
                """
                CREATE TABLE fissure_subscriptions__new (
                    user_id         INTEGER NOT NULL,
                    topic           TEXT    NOT NULL,
                    nodes_filter    TEXT    NOT NULL DEFAULT '',
                    planets_filter  TEXT    NOT NULL DEFAULT '',
                    missions_filter TEXT    NOT NULL DEFAULT '',
                    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (user_id, topic)
                );
                INSERT INTO fissure_subscriptions__new
                    (user_id, topic, nodes_filter, planets_filter, missions_filter, created_at)
                SELECT
                    user_id,
                    topic,
                    -- arbitrary but stable: keep the row with the first
                    -- created_at per (user, topic); MIN ensures determinism.
                    MIN(nodes_filter)    AS nodes_filter,
                    MIN(planets_filter)  AS planets_filter,
                    MIN(missions_filter) AS missions_filter,
                    MIN(created_at)      AS created_at
                FROM fissure_subscriptions
                GROUP BY user_id, topic;
                DROP TABLE fissure_subscriptions;
                ALTER TABLE fissure_subscriptions__new
                    RENAME TO fissure_subscriptions;
                CREATE INDEX IF NOT EXISTS idx_fissure_subs_topic
                    ON fissure_subscriptions (topic);
                """
            )

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
