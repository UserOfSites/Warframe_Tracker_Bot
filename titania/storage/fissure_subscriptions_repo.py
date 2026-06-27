from titania.domain.mission_type import parse_mission_type
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
    """Global per-user opt-in for fissure DM notifications, plus an optional
    per-row allowlist filter. Subscription and filter are independent:

    - ``subscribe`` / ``unsubscribe`` toggle the ``subscribed`` flag and are
      only ever called by the reaction handler. ``unsubscribe`` preserves
      the filter so re-subscribing later restores their preferences.
    - ``update_filter`` only touches the filter columns. If no row exists,
      one is created with ``subscribed=0`` — the user has pre-configured a
      filter without yet opting in.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def subscribe(self, user_id: int, topic: str) -> None:
        async with self._db.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO fissure_subscriptions (user_id, topic, subscribed)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, topic) DO UPDATE SET subscribed = 1
                """,
                (user_id, topic),
            )
        await self._db.commit()

    async def unsubscribe(self, user_id: int, topic: str) -> None:
        # Soft delete: keep the filter so a future re-subscribe brings it back.
        async with self._db.cursor() as cur:
            await cur.execute(
                "UPDATE fissure_subscriptions SET subscribed = 0 "
                "WHERE user_id = ? AND topic = ?",
                (user_id, topic),
            )
        await self._db.commit()

    async def is_subscribed(self, user_id: int, topic: str) -> bool:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT 1 FROM fissure_subscriptions "
                "WHERE user_id = ? AND topic = ? AND subscribed = 1",
                (user_id, topic),
            )
            row = await cur.fetchone()
        return row is not None

    async def list_user_topics(self, user_id: int) -> list[str]:
        """Topics this user is *actively* subscribed to (subscribed=1)."""
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT topic FROM fissure_subscriptions "
                "WHERE user_id = ? AND subscribed = 1 ORDER BY topic",
                (user_id,),
            )
            rows = await cur.fetchall()
        return [r[0] for r in rows]

    async def get_filter(
        self, user_id: int, topic: str
    ) -> SubscriptionFilter | None:
        """Filter for this (user, topic) regardless of subscription state.
        Returns ``None`` only when no row exists at all."""
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT nodes_filter, planets_filter, missions_filter "
                "FROM fissure_subscriptions "
                "WHERE user_id = ? AND topic = ?",
                (user_id, topic),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return _filter_from_row(row)

    async def update_filter(
        self, user_id: int, topic: str, new_filter: SubscriptionFilter
    ) -> None:
        """Update the filter columns. Does NOT change subscription state —
        if no row exists, a new one is created with ``subscribed=0``."""
        async with self._db.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO fissure_subscriptions
                    (user_id, topic, subscribed,
                     nodes_filter, planets_filter, missions_filter)
                VALUES (?, ?, 0, ?, ?, ?)
                ON CONFLICT(user_id, topic) DO UPDATE SET
                    nodes_filter    = excluded.nodes_filter,
                    planets_filter  = excluded.planets_filter,
                    missions_filter = excluded.missions_filter
                """,
                (
                    user_id,
                    topic,
                    _join(new_filter.nodes),
                    _join(new_filter.planets),
                    _join(frozenset(mt.value for mt in new_filter.mission_types)),
                ),
            )
        await self._db.commit()

    async def list_subscribers(self, topic: str) -> list[int]:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT user_id FROM fissure_subscriptions "
                "WHERE topic = ? AND subscribed = 1",
                (topic,),
            )
            rows = await cur.fetchall()
        return [int(r[0]) for r in rows]

    async def list_subscribers_with_filters(
        self, topic: str
    ) -> list[tuple[int, SubscriptionFilter]]:
        """Only actively-subscribed rows are returned — the notifier never DMs
        users who have pre-configured a filter without subscribing."""
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT user_id, nodes_filter, planets_filter, missions_filter "
                "FROM fissure_subscriptions WHERE topic = ? AND subscribed = 1",
                (topic,),
            )
            rows = await cur.fetchall()
        return [(int(r["user_id"]), _filter_from_row(r)) for r in rows]

    async def any_subscribers(self) -> bool:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT 1 FROM fissure_subscriptions WHERE subscribed = 1 LIMIT 1"
            )
            row = await cur.fetchone()
        return row is not None
