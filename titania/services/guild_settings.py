from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from titania.config import Config
from titania.domain.mission_type import MissionType, parse_mission_type


@dataclass(frozen=True)
class GuildSettings:
    allowed_mission_types: frozenset[MissionType]
    blocked_nodes: frozenset[str]
    pinned_nodes: frozenset[str]
    dojoshare_nodes: frozenset[str]
    locale: str

    @classmethod
    def from_config(cls, config: Config) -> "GuildSettings":
        return cls(
            allowed_mission_types=frozenset(
                parse_mission_type(m) for m in config.fast_missions()
            ),
            blocked_nodes=frozenset(),
            pinned_nodes=frozenset(),
            dojoshare_nodes=config.dojoshare_nodes(),
            locale=config.default_locale,
        )


# Async because the DB-backed repository implementation has to await SQLite.
# Tests can wrap a static value with `static_resolver(settings)` below.
GuildSettingsResolver = Callable[[int | None], Awaitable[GuildSettings]]


def static_resolver(settings: GuildSettings) -> GuildSettingsResolver:
    """Test helper: a resolver that always returns the same settings."""

    async def _resolve(_guild_id: int | None) -> GuildSettings:
        return settings

    return _resolve
