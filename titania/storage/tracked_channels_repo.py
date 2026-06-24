from dataclasses import dataclass

from titania.storage.db import Database


@dataclass(frozen=True)
class TrackedChannel:
    guild_id: int
    channel_id: int
    message_id: int


class TrackedChannelsRepository:
    """One auto-refresh channel per guild. Set with /track, removed with
    /untrack or automatically when the message is no longer reachable."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def list_all(self) -> list[TrackedChannel]:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT guild_id, channel_id, message_id FROM tracked_channels"
            )
            rows = await cur.fetchall()
        return [TrackedChannel(int(r["guild_id"]), int(r["channel_id"]), int(r["message_id"])) for r in rows]

    async def get(self, guild_id: int) -> TrackedChannel | None:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT guild_id, channel_id, message_id FROM tracked_channels "
                "WHERE guild_id = ?",
                (guild_id,),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return TrackedChannel(int(row["guild_id"]), int(row["channel_id"]), int(row["message_id"]))

    async def upsert(self, tc: TrackedChannel) -> None:
        async with self._db.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO tracked_channels (guild_id, channel_id, message_id, created_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    message_id = excluded.message_id,
                    created_at = datetime('now')
                """,
                (tc.guild_id, tc.channel_id, tc.message_id),
            )
        await self._db.commit()

    async def delete(self, guild_id: int) -> None:
        async with self._db.cursor() as cur:
            await cur.execute(
                "DELETE FROM tracked_channels WHERE guild_id = ?", (guild_id,)
            )
        await self._db.commit()
