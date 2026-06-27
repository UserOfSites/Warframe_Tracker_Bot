from titania.config import Config
from titania.domain.mission_type import MissionType, parse_mission_type
from titania.services.guild_settings import GuildSettings
from titania.storage.db import Database


def _join(values: frozenset[str]) -> str:
    return ",".join(sorted(values))


def _split(raw: str) -> frozenset[str]:
    return frozenset(s.strip() for s in raw.split(",") if s.strip())


def _to_mission_types(raw: str) -> frozenset[MissionType]:
    return frozenset(parse_mission_type(s) for s in _split(raw))


def _from_mission_types(types: frozenset[MissionType]) -> str:
    return _join(frozenset(t.value for t in types))


class GuildSettingsRepository:
    """Persistence-backed guild settings.

    Reads return the row if present, else the bot-wide default (so guilds that
    have never run a `/settings` command silently inherit defaults). Writes
    insert-or-update.
    """

    def __init__(self, db: Database, config: Config) -> None:
        self._db = db
        self._default = GuildSettings.from_config(config)

    @property
    def default(self) -> GuildSettings:
        return self._default

    async def get(self, guild_id: int | None) -> GuildSettings:
        if guild_id is None:
            return self._default
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT locale, allowed_mission_types, blocked_nodes, "
                "pinned_nodes, dojoshare_nodes, excellent_nodes, good_nodes "
                "FROM guild_settings WHERE guild_id = ?",
                (guild_id,),
            )
            row = await cur.fetchone()
        if row is None:
            return self._default
        return GuildSettings(
            allowed_mission_types=_to_mission_types(row["allowed_mission_types"]),
            blocked_nodes=_split(row["blocked_nodes"]),
            pinned_nodes=_split(row["pinned_nodes"]),
            dojoshare_nodes=_split(row["dojoshare_nodes"]),
            excellent_nodes=_split(row["excellent_nodes"]),
            good_nodes=_split(row["good_nodes"]),
            locale=row["locale"],
        )

    async def save(self, guild_id: int, settings: GuildSettings) -> None:
        async with self._db.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO guild_settings
                    (guild_id, locale, allowed_mission_types, blocked_nodes,
                     pinned_nodes, dojoshare_nodes,
                     excellent_nodes, good_nodes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(guild_id) DO UPDATE SET
                    locale = excluded.locale,
                    allowed_mission_types = excluded.allowed_mission_types,
                    blocked_nodes = excluded.blocked_nodes,
                    pinned_nodes = excluded.pinned_nodes,
                    dojoshare_nodes = excluded.dojoshare_nodes,
                    excellent_nodes = excluded.excellent_nodes,
                    good_nodes = excluded.good_nodes,
                    updated_at = datetime('now')
                """,
                (
                    guild_id,
                    settings.locale,
                    _from_mission_types(settings.allowed_mission_types),
                    _join(settings.blocked_nodes),
                    _join(settings.pinned_nodes),
                    _join(settings.dojoshare_nodes),
                    _join(settings.excellent_nodes),
                    _join(settings.good_nodes),
                ),
            )
        await self._db.commit()
