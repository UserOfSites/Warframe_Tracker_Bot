"""Ayatan sculpture hourly rotation.

Community-discovered mechanic: which Ayatan sculpture spawns in general
missions is fixed on a 24-slot hourly cycle, all times in **UTC-4** (fixed
offset, no DST). Source: r/Warframe post 1trhmki (screenshot data below).
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


# Hourly rotation in UTC-4. Index N = sculpture spawning during the UTC-4 hour
# that starts at N:00. From the Reddit rotation screenshot:
#
#   00 Vaya    01 Sah     02 Vaya    03 Valana  04 Valana  05 Piv
#   06 Vaya    07 Vaya    08 Sah     09 Orta    10 Piv     11 Ayr
#   12 Valana  13 Piv     14 Piv     15 Orta    16 Valana  17 Sah
#   18 Vaya    19 Sah     20 Ayr     21 Valana  22 Piv     23 Valana
#
# Premium windows: 09:00 & 15:00 (Orta, 2700 endo).
# Worst windows:   11:00 & 20:00 (Ayr, 1425 endo).
ROTATION_UTC4: tuple[str, ...] = (
    "Vaya", "Sah", "Vaya", "Valana", "Valana", "Piv",
    "Vaya", "Vaya", "Sah", "Orta", "Piv", "Ayr",
    "Valana", "Piv", "Piv", "Orta", "Valana", "Sah",
    "Vaya", "Sah", "Ayr", "Valana", "Piv", "Valana",
)
assert len(ROTATION_UTC4) == 24


@dataclass(frozen=True)
class AyatanSlot:
    """Snapshot of the rotation at a specific moment in time."""

    current: AyatanSculpture
    next: AyatanSculpture
    changes_at: datetime  # UTC — always aware, top-of-next-hour in UTC-4
