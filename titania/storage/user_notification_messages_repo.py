from titania.storage.db import Database


class UserNotificationMessagesRepository:
    """The (channel, message) the notifier should keep editing as the user's
    personal subscription summary. Replaces the per-fissure DM flood with a
    single, in-place-updated message.

    Records are created lazily by the notifier when it first DMs a user; the
    notifier deletes the record (and lets a new one be created next tick) if
    the message has been removed user-side.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, user_id: int) -> tuple[int, int] | None:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT channel_id, message_id FROM user_notification_messages "
                "WHERE user_id = ?",
                (user_id,),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return (int(row["channel_id"]), int(row["message_id"]))

    async def upsert(
        self, user_id: int, channel_id: int, message_id: int
    ) -> None:
        async with self._db.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO user_notification_messages
                    (user_id, channel_id, message_id, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(user_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    message_id = excluded.message_id,
                    updated_at = datetime('now')
                """,
                (user_id, channel_id, message_id),
            )
        await self._db.commit()

    async def delete(self, user_id: int) -> None:
        async with self._db.cursor() as cur:
            await cur.execute(
                "DELETE FROM user_notification_messages WHERE user_id = ?",
                (user_id,),
            )
        await self._db.commit()
