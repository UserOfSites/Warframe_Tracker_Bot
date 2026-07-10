"""Ayatan sculpture hourly rotation.

Community-discovered mechanic: which Ayatan sculpture spawns in general
missions is fixed on a 24-slot hourly cycle, anchored to **UTC-4** (as
originally labelled in the r/Warframe reference table 1trhmki).

**Empirical calibration:** twelve independently-observed Baro-Ayatan runs
from a European (CEST) tester scored 10/12 against the UTC-4 anchor and
5/12 against a UTC anchor. The two UTC-4 outliers both landed within
15 minutes of an hour boundary, consistent with observation noise rather
than a systematic anchor error. See ``test_ayatan_service.py`` for the
full observation set.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AyatanSculpture:
    name: str
    full_endo: int  # Endo value with all 4 stars slotted (2 Amber + 2 Cyan for most)


AYATAN_SCULPTURES: dict[str, AyatanSculpture] = {
    "Orta":   AyatanSculpture(name="Orta",   full_endo=2700),
    "Vaya":   AyatanSculpture(name="Vaya",   full_endo=1800),
    "Piv":    AyatanSculpture(name="Piv",    full_endo=1725),
    "Valana": AyatanSculpture(name="Valana", full_endo=1575),
    "Sah":    AyatanSculpture(name="Sah",    full_endo=1500),
    "Ayr":    AyatanSculpture(name="Ayr",    full_endo=1425),
}


# Hourly rotation indexed by **UTC-4 hour**. Index N = sculpture that spawns
# during the UTC-4 hour starting at N:00.
#
#   00 Vaya    01 Sah     02 Vaya    03 Valana  04 Valana  05 Piv
#   06 Vaya    07 Vaya    08 Sah     09 Orta    10 Piv     11 Ayr
#   12 Valana  13 Piv     14 Piv     15 Orta    16 Valana  17 Sah
#   18 Vaya    19 Sah     20 Ayr     21 Valana  22 Piv     23 Valana
#
# Premium windows: 09:00 & 15:00 UTC-4 (Orta, 2700 endo).
# Worst windows:   11:00 & 20:00 UTC-4 (Ayr, 1425 endo).
ROTATION_UTC4: tuple[str, ...] = (
    "Vaya", "Sah", "Vaya", "Valana", "Valana", "Piv",
    "Vaya", "Vaya", "Sah", "Orta", "Piv", "Ayr",
    "Valana", "Piv", "Piv", "Orta", "Valana", "Sah",
    "Vaya", "Sah", "Ayr", "Valana", "Piv", "Valana",
)
assert len(ROTATION_UTC4) == 24


@dataclass(frozen=True)
class AyatanSlot:
    """Snapshot of the rotation at a specific moment in time.

    ``next`` and ``next_change_at`` skip over consecutive hours that keep the
    same sculpture — Valana holds slots 3+4, 12, 16, 21+23 for example, so
    reporting the "next hour" would just repeat "Valana" and confuse readers.
    ``next`` is the sculpture at the first *different* hour, and
    ``next_change_at`` is when the current one actually stops spawning.
    """

    current: AyatanSculpture
    next: AyatanSculpture
    next_change_at: datetime  # UTC — when `current` stops and `next` starts
