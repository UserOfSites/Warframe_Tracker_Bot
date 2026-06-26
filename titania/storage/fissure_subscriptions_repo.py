from titania.domain.mission_type import MissionType, parse_mission_type
from titania.domain.subscription_filter import SubscriptionFilter
from titania.storage.db import Database


def _join(values: frozenset[str]) -> str:
    return ",".join(sorted(values))


def _split(raw: str) -> frozenset[str]:
    return frozenset(s.strip() for s in raw.split(",") if s.strip())


def _filter_from_row(row) -> SubscriptionFilter:
    return SubscriptionFilter(
        nodes=_split(row["nodes_filter"]),
        planets=_split(row["planets_filter"]),
        mission_types=frozenset(
            parse_mission_type(s) for s in _split(row["missions_filter"])
        ),
    )


class FissureSubscriptionsRepository:
    """Per-(guild, user, topic) opt-in for fissure DM notifications, plus an
    optional per-row allowlist filter (nodes / planets / mission types). Empty
    filter columns mean "any" — i.e. backwards-compatible with subscriptions
    created before filtering existed.
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

    async def get_filter(
        self, guild_id: int, user_id: int, topic: str
    ) -> SubscriptionFilter | None:
        """Return the filter for this subscription, or None if not subscribed."""
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT nodes_filter, planets_filter, missions_filter "
                "FROM fissure_subscriptions "
                "WHERE guild_id = ? AND user_id = ? AND topic = ?",
                (guild_id, user_id, topic),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return _filter_from_row(row)

    async def update_filter(
        self,
        guild_id: int,
        user_id: int,
        topic: str,
        new_filter: SubscriptionFilter,
    ) -> None:
        """Update filter columns on an existing subscription. Idempotently
        creates the row first so callers don't have to subscribe separately."""
        await self.subscribe(guild_id, user_id, topic)
        async with self._db.cursor() as cur:
            await cur.execute(
                "UPDATE fissure_subscriptions "
                "SET nodes_filter = ?, planets_filter = ?, missions_filter = ? "
                "WHERE guild_id = ? AND user_id = ? AND topic = ?",
                (
                    _join(new_filter.nodes),
                    _join(new_filter.planets),
                    _join(frozenset(mt.value for mt in new_filter.mission_types)),
                    guild_id,
                    user_id,
                    topic,
                ),
            )
        await self._db.commit()

    async def list_subscribers(
        self, guild_id: int, topic: str
    ) -> list[int]:
        """Just user_ids — kept for callers that don't need filters."""
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT user_id FROM fissure_subscriptions "
                "WHERE guild_id = ? AND topic = ?",
                (guild_id, topic),
            )
            rows = await cur.fetchall()
        return [int(r[0]) for r in rows]

    async def list_subscribers_with_filters(
        self, guild_id: int, topic: str
    ) -> list[tuple[int, SubscriptionFilter]]:
        """Subscribers paired with their personal allowlist filter.
        Used by the notifier to narrow each user's DMs."""
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT user_id, nodes_filter, planets_filter, missions_filter "
                "FROM fissure_subscriptions "
                "WHERE guild_id = ? AND topic = ?",
                (guild_id, topic),
            )
            rows = await cur.fetchall()
        return [(int(r["user_id"]), _filter_from_row(r)) for r in rows]

    async def list_subscribed_guilds(self) -> list[int]:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT DISTINCT guild_id FROM fissure_subscriptions"
            )
            rows = await cur.fetchall()
        return [int(r[0]) for r in rows]
