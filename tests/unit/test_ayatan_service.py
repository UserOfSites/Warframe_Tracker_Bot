from datetime import datetime, timedelta, timezone

import pytest

from titania.domain.ayatan import AYATAN_SCULPTURES, ROTATION_UTC4
from titania.services.ayatan_service import AyatanService


UTC = timezone.utc
UTC_MINUS_4 = timezone(timedelta(hours=-4))


@pytest.fixture
def svc() -> AyatanService:
    return AyatanService()


def test_current_slot_at_midnight_utc4_returns_00_slot(svc: AyatanService):
    # 00:15 UTC-4 = 04:15 UTC. Rotation slot 0 = Vaya.
    now = datetime(2026, 6, 24, 4, 15, tzinfo=UTC)
    slot = svc.current_slot(now)
    assert slot.current.name == ROTATION_UTC4[0]  # "Vaya"
    assert slot.next.name == ROTATION_UTC4[1]     # "Sah"


def test_current_slot_uses_ceiling_hour_boundary(svc: AyatanService):
    # 15:59 UTC-4 → still hour 15 (Orta), rotates to 16 (Valana) at 16:00.
    now = datetime(2026, 6, 24, 19, 59, tzinfo=UTC)  # 15:59 UTC-4
    slot = svc.current_slot(now)
    assert slot.current.name == "Orta"
    assert slot.next.name == "Valana"


def test_next_change_at_wraps_across_midnight(svc: AyatanService):
    # 23:30 UTC-4 → current is 23 (Valana), next hour is 00 (Vaya) — next day.
    now_utc = datetime(2026, 6, 25, 3, 30, tzinfo=UTC)  # 23:30 UTC-4 on 06-24
    slot = svc.current_slot(now_utc)
    assert slot.current.name == "Valana"
    assert slot.next.name == "Vaya"
    # changes_at is 04:00 UTC on 2026-06-25 = 00:00 UTC-4 on 2026-06-25
    assert slot.next_change_at == datetime(2026, 6, 25, 4, 0, tzinfo=UTC)


def test_changes_at_is_top_of_next_utc4_hour(svc: AyatanService):
    # 09:23 UTC-4 = Orta. Next different at 10:00 UTC-4 = Piv = 14:00 UTC.
    now = datetime(2026, 6, 24, 13, 23, tzinfo=UTC)  # 09:23 UTC-4
    slot = svc.current_slot(now)
    assert slot.current.name == "Orta"
    assert slot.next.name == "Piv"
    assert slot.next_change_at == datetime(2026, 6, 24, 14, 0, tzinfo=UTC)


def test_next_skips_consecutive_same_sculpture(svc: AyatanService):
    """Valana holds slots 3 and 4 in a row. At 03:00 UTC-4, ``next`` must
    be the *following different* sculpture (Piv at slot 5), not another
    Valana."""
    # 03:00 UTC-4 = 07:00 UTC.
    now = datetime(2026, 6, 24, 7, 0, tzinfo=UTC)
    slot = svc.current_slot(now)
    assert slot.current.name == "Valana"
    assert slot.next.name == "Piv"  # NOT "Valana"
    # Changeover at 05:00 UTC-4 = 09:00 UTC.
    assert slot.next_change_at == datetime(2026, 6, 24, 9, 0, tzinfo=UTC)


def test_next_skips_consecutive_same_sculpture_mid_hour(svc: AyatanService):
    # 03:24 UTC-4 (matches the reported screenshot: Valana → Valana bug).
    now = datetime(2026, 6, 24, 7, 24, tzinfo=UTC)
    slot = svc.current_slot(now)
    assert slot.current.name == "Valana"
    assert slot.next.name == "Piv"
    assert slot.next_change_at == datetime(2026, 6, 24, 9, 0, tzinfo=UTC)


def test_all_24_slots_reachable_and_valid(svc: AyatanService):
    seen = set()
    # Sweep every hour in UTC-4 for one day.
    base = datetime(2026, 6, 24, 4, 0, tzinfo=UTC)  # 00:00 UTC-4
    for hour in range(24):
        now = base + timedelta(hours=hour)
        slot = svc.current_slot(now)
        assert slot.current.name in AYATAN_SCULPTURES
        assert slot.next.name in AYATAN_SCULPTURES
        seen.add(slot.current.name)
    # All 6 sculptures appear at least once in the day (matches the Reddit
    # windows-per-day column: Orta 2, Vaya 5, Piv 5, Valana 6, Sah 4, Ayr 2).
    assert seen == set(AYATAN_SCULPTURES.keys())


def _at_utc4(hour_utc4: int) -> datetime:
    """Build a UTC datetime that projects to ``hour_utc4:00`` in UTC-4."""
    return datetime(2026, 6, 24, 0, 0, tzinfo=UTC_MINUS_4).replace(
        hour=hour_utc4
    ).astimezone(UTC)


def test_premium_windows_at_09_and_15_show_orta(svc: AyatanService):
    for hour_utc4 in (9, 15):
        slot = svc.current_slot(_at_utc4(hour_utc4))
        assert slot.current.name == "Orta"
        assert slot.current.full_endo == 2700


def test_worst_windows_at_11_and_20_show_ayr(svc: AyatanService):
    for hour_utc4 in (11, 20):
        slot = svc.current_slot(_at_utc4(hour_utc4))
        assert slot.current.name == "Ayr"
        assert slot.current.full_endo == 1425


def test_naive_datetime_treated_as_utc(svc: AyatanService):
    """Callers occasionally pass naive datetimes (e.g. from freezegun); the
    service should still return a sensible slot instead of raising."""
    naive = datetime(2026, 6, 24, 13, 23)  # equivalent to 09:23 UTC-4
    slot = svc.current_slot(naive)
    assert slot.current.name == "Orta"
