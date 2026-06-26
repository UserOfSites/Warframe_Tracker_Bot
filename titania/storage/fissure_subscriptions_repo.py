from titania.storage.db import Database


class FissureSubscriptionsRepository:
    """Per-(guild, user, topic) opt-in for fissure DM notifications.

    Subscriptions are guild-scoped — a user who's a member of multiple
    servers must click the buttons in each server they want notifications
    from. The compound PRIMARY KEY makes ``subscribe`` idempotent.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def subscribe(self, guild_id: int, user_id: int, topic: str) -> None:
        async with self._db.cursor() as cur:
            await cur.execute(
                "INSERT OR IGNORE INTO fissure_subscriptions "
                "(guild_id, user_id, topic) VALUES (?, ?, ?)",
                (guild_id, user_id, topic),
            )
        await self._db.commit()

    async def unsubscribe(self, guild_id: int, user_id: int, topic: str) -> None:
        async with self._db.cursor() as cur:
            await cur.execute(
                "DELETE FROM fissure_subscriptions "
                "WHERE guild_id = ? AND user_id = ? AND topic = ?",
                (guild_id, user_id, topic),
            )
        await self._db.commit()

    async def is_subscribed(
        self, guild_id: int, user_id: int, topic: str
    ) -> bool:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT 1 FROM fissure_subscriptions "
                "WHERE guild_id = ? AND user_id = ? AND topic = ?",
                (guild_id, user_id, topic),
            )
            row = await cur.fetchone()
        return row is not None

    async def list_user_topics(self, guild_id: int, user_id: int) -> list[str]:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT topic FROM fissure_subscriptions "
                "WHERE guild_id = ? AND user_id = ? ORDER BY topic",
                (guild_id, user_id),
            )
            rows = await cur.fetchall()
        return [r[0] for r in rows]

    async def list_subscribers(
        self, guild_id: int, topic: str
    ) -> list[int]:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT user_id FROM fissure_subscriptions "
                "WHERE guild_id = ? AND topic = ?",
                (guild_id, topic),
            )
            rows = await cur.fetchall()
        return [int(r[0]) for r in rows]

    async def list_subscribed_guilds(self) -> list[int]:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT DISTINCT guild_id FROM fissure_subscriptions"
            )
            rows = await cur.fetchall()
        return [int(r[0]) for r in rows]
