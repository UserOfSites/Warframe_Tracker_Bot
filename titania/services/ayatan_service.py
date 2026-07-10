from datetime import datetime, timedelta, timezone

from titania.domain.ayatan import (
    AYATAN_SCULPTURES,
    ROTATION_UTC4,
    AyatanSlot,
)

# Fixed UTC-4 offset — no DST. See ``titania.domain.ayatan`` for the anchor
# choice rationale (empirical fit against 12 in-game observations).
_UTC_MINUS_4 = timezone(timedelta(hours=-4), name="UTC-4")


class AyatanService:
    """Stateless lookup: which sculpture is spawning right now, when the
    current one *actually* rotates away, and what comes next. Consecutive
    same-sculpture hours are collapsed so ``next`` never repeats ``current``
    (Valana holds six hours, several of them adjacent)."""

    def current_slot(self, now: datetime | None = None) -> AyatanSlot:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now_utc4 = now.astimezone(_UTC_MINUS_4)
        current_hour = now_utc4.hour
        current_name = ROTATION_UTC4[current_hour]

        # Walk forward until we hit a different sculpture. 24 iterations is a
        # safe cap and the loop is guaranteed to terminate because the
        # rotation contains at least two distinct sculptures.
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
        raise RuntimeError("rotation table only contains one sculpture")
