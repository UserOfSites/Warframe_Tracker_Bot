from enum import StrEnum


class Era(StrEnum):
    LITH = "Lith"
    MESO = "Meso"
    NEO = "Neo"
    AXI = "Axi"
    REQUIEM = "Requiem"
    OMNIA = "Omnia"


ERA_TIER: dict[Era, int] = {
    Era.LITH: 1,
    Era.MESO: 2,
    Era.NEO: 3,
    Era.AXI: 4,
    Era.REQUIEM: 5,
    Era.OMNIA: 6,
}
