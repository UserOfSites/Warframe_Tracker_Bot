from titania.storage.db import Database


class UserPreferencesRepository:
    """Per-user preferences keyed by Discord user_id. Currently just the
    locale used for DM notifications and the welcome embed.

    A row is created lazily on the first ``set_locale`` call; reads for a
    user with no row fall back to ``'en'``.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_locale(self, user_id: int) -> str:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT locale FROM user_preferences WHERE user_id = ?",
                (user_id,),
            )
            row = await cur.fetchone()
        return row[0] if row else "en"

    async def set_locale(self, user_id: int, locale: str) -> None:
        async with self._db.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO user_preferences (user_id, locale, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(user_id) DO UPDATE SET
                    locale = excluded.locale,
                    updated_at = datetime('now')
                """,
                (user_id, locale),
            )
        await self._db.commit()

    async def is_muted(self, user_id: int) -> bool:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT muted FROM user_preferences WHERE user_id = ?",
                (user_id,),
            )
            row = await cur.fetchone()
        return bool(row[0]) if row else False

    async def set_muted(self, user_id: int, muted: bool) -> None:
        async with self._db.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO user_preferences (user_id, muted, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(user_id) DO UPDATE SET
                    muted = excluded.muted,
                    updated_at = datetime('now')
                """,
                (user_id, 1 if muted else 0),
            )
        await self._db.commit()
