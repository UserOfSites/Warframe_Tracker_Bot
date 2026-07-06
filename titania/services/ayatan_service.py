from datetime import datetime, timedelta, timezone

from titania.domain.ayatan import (
    AYATAN_SCULPTURES,
    ROTATION_UTC4,
    AyatanSlot,
)

# Fixed offset — the Reddit table is labelled "EDT / UTC-4" but the rotation
# itself is anchored to UTC-4 as a fixed offset (community shorthand). Using
# tzinfo instead of zoneinfo keeps this deterministic across DST boundaries.
_UTC_MINUS_4 = timezone(timedelta(hours=-4), name="UTC-4")


class AyatanService:
    """Stateless lookup: which sculpture is spawning right now, when the next
    rotation happens, and what comes after. Nothing to inject — the rotation
    is a compile-time constant."""

    def current_slot(self, now: datetime | None = None) -> AyatanSlot:
        # Always work in UTC first, then project to UTC-4 for the hour lookup.
        # If the caller passed a naive datetime we treat it as UTC (used only
        # by tests; the bot itself always passes an aware one).
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now_utc4 = now.astimezone(_UTC_MINUS_4)
        current_hour = now_utc4.hour

        # Next rotation boundary is the top of the *next* hour in UTC-4.
        next_change_utc4 = now_utc4.replace(
            minute=0, second=0, microsecond=0
        ) + timedelta(hours=1)
        next_hour = next_change_utc4.hour  # already 0..23, wraps at midnight

        return AyatanSlot(
            current=AYATAN_SCULPTURES[ROTATION_UTC4[current_hour]],
            next=AYATAN_SCULPTURES[ROTATION_UTC4[next_hour]],
            changes_at=next_change_utc4.astimezone(timezone.utc),
        )
