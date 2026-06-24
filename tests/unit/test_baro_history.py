from datetime import date

from titania.data.baro.history import _parse_lua

_SAMPLE = """\
-- Example data (slimmed down version of the wiki module)
return {
    ["Items"] = {
        ["Prisma Grakata"] = {
            CreditCost = 175000,
            DucatCost = 525,
            Image = "PrismaGrakata.png",
            Link = "Prisma Grakata",
            Name = "Prisma Grakata",
            OfferingDates = {
                "2025-04-11",
                "2025-09-05",
                "2026-03-20",
            },
            PcOfferingDates = {
                "2014-12-12",
                "2015-08-21",
            },
            ConsoleOfferingDates = {
                "2015-01-10",
            },
            Type = "Weapon",
        },
        ["Octavia's Anthem"] = {
            CreditCost = 50000,
            DucatCost = 100,
            Image = "OctaviaAnthem.png",
            Name = "Octavia's Anthem",
            OfferingDates = { "2026-01-09" },
            Type = "Consumable",
        },
    },
}
"""


def test_parse_lua_extracts_items():
    items = _parse_lua(_SAMPLE)
    assert set(items.keys()) == {"Prisma Grakata", "Octavia's Anthem"}


def test_parse_lua_merges_dates_across_platforms_dedup():
    items = _parse_lua(_SAMPLE)
    prisma = items["Prisma Grakata"]
    # 3 cross-platform + 2 PC-only + 1 console-only = 6 unique dates
    assert len(prisma.appearances) == 6
    assert prisma.appearances[0] == date(2014, 12, 12)
    assert prisma.appearances[-1] == date(2026, 3, 20)


def test_parse_lua_captures_cost_metadata():
    items = _parse_lua(_SAMPLE)
    prisma = items["Prisma Grakata"]
    assert prisma.ducat_cost == 525
    assert prisma.credit_cost == 175000
    assert prisma.image == "PrismaGrakata.png"
    assert prisma.item_type == "Weapon"


def test_last_appearance_returns_most_recent():
    items = _parse_lua(_SAMPLE)
    assert items["Prisma Grakata"].last_appearance == date(2026, 3, 20)
    assert items["Octavia's Anthem"].last_appearance == date(2026, 1, 9)
