from titania.storage.db import Database
from titania.storage.tracked_channels_repo import TrackedChannel


class TrackedVendorsRepository:
    """One auto-refresh channel per guild for the vendors embed. Same shape
    as the fissures tracked channel; separate table so guilds can have one of
    each in different channels."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def list_all(self) -> list[TrackedChannel]:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT guild_id, channel_id, message_id FROM tracked_vendors_channels"
            )
            rows = await cur.fetchall()
        return [
            TrackedChannel(int(r["guild_id"]), int(r["channel_id"]), int(r["message_id"]))
            for r in rows
        ]

    async def get(self, guild_id: int) -> TrackedChannel | None:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT guild_id, channel_id, message_id FROM tracked_vendors_channels "
                "WHERE guild_id = ?",
                (guild_id,),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return TrackedChannel(
            int(row["guild_id"]), int(row["channel_id"]), int(row["message_id"])
        )

    async def upsert(self, tc: TrackedChannel) -> None:
        async with self._db.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO tracked_vendors_channels (guild_id, channel_id, message_id, created_at)
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
                "DELETE FROM tracked_vendors_channels WHERE guild_id = ?", (guild_id,)
            )
        await self._db.commit()
