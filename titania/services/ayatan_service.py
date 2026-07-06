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
    """Stateless lookup: which sculpture is spawning right now, when the
    current one *actually* rotates away, and what comes next. Consecutive
    same-sculpture hours are collapsed so ``next`` never repeats ``current``
    — otherwise the embed would show pointless "Next: Valana" lines when
    Valana holds two hours in a row."""

    def current_slot(self, now: datetime | None = None) -> AyatanSlot:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now_utc4 = now.astimezone(_UTC_MINUS_4)
        current_hour = now_utc4.hour
        current_name = ROTATION_UTC4[current_hour]

        # Walk forward until we hit a different sculpture. Max 24 iterations
        # is a safe cap (the whole rotation is 24 slots) and the loop is
        # guaranteed to terminate because the rotation contains at least
        # two distinct sculptures.
        top_of_hour = now_utc4.replace(minute=0, second=0, microsecond=0)
        for offset in range(1, 25):
            candidate_hour = (current_hour + offset) % 24
            candidate_name = ROTATION_UTC4[candidate_hour]
            if candidate_name != current_name:
                next_change_utc4 = top_of_hour + timedelta(hours=offset)
                return AyatanSlot(
                    current=AYATAN_SCULPTURES[current_name],
                    next=AYATAN_SCULPTURES[candidate_name],
                    next_change_at=next_change_utc4.astimezone(timezone.utc),
                )
        # Impossible in practice — the rotation has at least two sculptures.
        raise RuntimeError("rotation table only contains one sculpture")
