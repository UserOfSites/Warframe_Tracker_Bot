from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from titania.data.baro.history import BaroItemHistory, humanize_since
from titania.domain.baro import VoidTraderState
from titania.services.baro_service import BaroService


def _stub_history(items: dict[str, BaroItemHistory]):
    history = MagicMock()

    async def _lookup(names):
        return {n: items[n] for n in names if n in items}

    history.lookup = AsyncMock(side_effect=_lookup)
    return history


def _source(payload: dict):
    src = MagicMock()
    src.fetch_void_trader = AsyncMock(return_value=payload)
    return src


async def test_state_when_baro_not_present():
    src = _source(
        {
            "character": "Baro Ki'Teer",
            "location": "Orcus Relay (Pluto)",
            "activation": "2099-01-08T13:00:00.000Z",
            "expiry": "2099-01-10T13:00:00.000Z",
            "inventory": [],
        }
    )
    svc = BaroService(src, _stub_history({}))
    state = await svc.fetch_state()
    assert state.character == "Baro Ki'Teer"
    assert state.location == "Orcus Relay (Pluto)"
    assert state.inventory == ()
    assert state.is_present is False


async def test_state_when_baro_is_present():
    src = _source(
        {
            "character": "Baro Ki'Teer",
            "location": "Orcus Relay (Pluto)",
            "activation": "2026-06-26T13:00:00.000Z",
            "expiry": "2026-06-28T13:00:00.000Z",
            "inventory": [
                {"item": "Prisma Grakata", "ducats": 525, "credits": 175000},
                {"item": "Octavia's Anthem", "ducats": 100, "credits": None},
            ],
        }
    )
    svc = BaroService(src, _stub_history({}))
    state = await svc.fetch_state()
    assert state.is_present is True
    assert len(state.inventory) == 2
    assert state.inventory[0].name == "Prisma Grakata"
    assert state.inventory[0].ducats == 525
    assert state.inventory[1].credits is None


async def test_board_skips_history_lookup_when_not_present():
    src = _source({"inventory": [], "activation": "2099-01-01T00:00:00.000Z",
                   "expiry": "2099-01-01T00:00:00.000Z"})
    history = _stub_history({})
    svc = BaroService(src, history)
    board = await svc.board()
    assert board.state.is_present is False
    assert board.enriched_inventory == ()
    history.lookup.assert_not_called()


async def test_board_enriches_inventory_with_last_appearance():
    history_data = {
        "Prisma Grakata": BaroItemHistory(
            name="Prisma Grakata",
            ducat_cost=525,
            credit_cost=175000,
            image="PrismaGrakata.png",
            item_type="Weapon",
            appearances=(date(2024, 1, 5), date(2024, 7, 19), date(2026, 6, 26)),
        )
    }
    src = _source(
        {
            "character": "Baro Ki'Teer",
            "location": "Orcus Relay (Pluto)",
            "activation": "2026-06-26T13:00:00.000Z",
            "expiry": "2026-06-28T13:00:00.000Z",
            "inventory": [
                {"item": "Prisma Grakata", "ducats": 525, "credits": 175000}
            ],
        }
    )
    svc = BaroService(src, _stub_history(history_data))
    board = await svc.board()
    assert len(board.enriched_inventory) == 1
    enriched = board.enriched_inventory[0]
    assert enriched.name == "Prisma Grakata"
    # Current visit is 2026-06-26 — last_appearance should be the visit BEFORE that.
    assert enriched.last_appearance == date(2024, 7, 19)
    assert enriched.total_appearances == 3


async def test_repeated_calls_during_same_visit_dont_refetch_history():
    """Inventory + activation identical → enriched list comes from per-visit
    cache; the history client is consulted exactly once."""
    history_data = {
        "Prisma Grakata": BaroItemHistory(
            name="Prisma Grakata",
            ducat_cost=525,
            credit_cost=175000,
            image="PrismaGrakata.png",
            item_type="Weapon",
            appearances=(date(2024, 1, 5), date(2026, 6, 26)),
        )
    }
    history = _stub_history(history_data)
    src = _source(
        {
            "character": "Baro Ki'Teer",
            "location": "Orcus Relay (Pluto)",
            "activation": "2026-06-26T13:00:00.000Z",
            "expiry": "2026-06-28T13:00:00.000Z",
            "inventory": [{"item": "Prisma Grakata", "ducats": 525, "credits": 175000}],
        }
    )
    svc = BaroService(src, history)
    # Three "refresh ticks" while Baro is present.
    for _ in range(3):
        await svc.board()
    assert history.lookup.call_count == 1


async def test_inventory_rotation_invalidates_visit_cache():
    history_data = {
        "Prisma Grakata": BaroItemHistory(
            name="Prisma Grakata",
            ducat_cost=525,
            credit_cost=175000,
            image="PrismaGrakata.png",
            item_type="Weapon",
            appearances=(date(2024, 1, 5),),
        ),
        "Prisma Skana": BaroItemHistory(
            name="Prisma Skana",
            ducat_cost=400,
            credit_cost=150000,
            image="PrismaSkana.png",
            item_type="Melee",
            appearances=(date(2024, 5, 1),),
        ),
    }
    history = _stub_history(history_data)
    src = MagicMock()
    payloads = [
        {
            "character": "Baro Ki'Teer",
            "location": "Orcus Relay (Pluto)",
            "activation": "2026-06-26T13:00:00.000Z",
            "expiry": "2026-06-28T13:00:00.000Z",
            "inventory": [{"item": "Prisma Grakata", "ducats": 525, "credits": 175000}],
        },
        {
            "character": "Baro Ki'Teer",
            "location": "Orcus Relay (Pluto)",
            "activation": "2026-06-26T13:00:00.000Z",
            "expiry": "2026-06-28T13:00:00.000Z",
            "inventory": [
                {"item": "Prisma Grakata", "ducats": 525, "credits": 175000},
                {"item": "Prisma Skana", "ducats": 400, "credits": 150000},
            ],
        },
    ]
    src.fetch_void_trader = AsyncMock(side_effect=payloads)
    svc = BaroService(src, history)
    await svc.board()
    await svc.board()
    assert history.lookup.call_count == 2  # different inventory → re-query


async def test_baro_leaving_drops_visit_cache():
    history = _stub_history({})
    src = MagicMock()
    src.fetch_void_trader = AsyncMock(
        side_effect=[
            {
                "character": "Baro Ki'Teer",
                "location": "Orcus Relay (Pluto)",
                "activation": "2026-06-26T13:00:00.000Z",
                "expiry": "2026-06-28T13:00:00.000Z",
                "inventory": [{"item": "Prisma Grakata", "ducats": 525}],
            },
            {
                # Next call: Baro has left, inventory empty
                "character": "Baro Ki'Teer",
                "location": "Orcus Relay (Pluto)",
                "activation": "2026-07-10T13:00:00.000Z",
                "expiry": "2026-07-12T13:00:00.000Z",
                "inventory": [],
            },
        ]
    )
    svc = BaroService(src, history)
    await svc.board()  # present, caches
    board = await svc.board()  # absent, should clear cache
    assert board.enriched_inventory == ()
    assert svc._cached_visit_key is None  # type: ignore[attr-defined]


async def test_unknown_item_in_inventory_returns_first_appearance_marker():
    src = _source(
        {
            "character": "Baro Ki'Teer",
            "location": "Orcus Relay (Pluto)",
            "activation": "2026-06-26T13:00:00.000Z",
            "expiry": "2026-06-28T13:00:00.000Z",
            "inventory": [{"item": "Brand-new Mystery Item", "ducats": 50}],
        }
    )
    svc = BaroService(src, _stub_history({}))
    board = await svc.board()
    enriched = board.enriched_inventory[0]
    assert enriched.last_appearance is None
    assert enriched.total_appearances == 0


def test_humanize_since_formats_compactly():
    now = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)
    assert humanize_since(None, now) == "never"
    # 7d 12h ago
    assert humanize_since(date(2026, 6, 17), now).endswith("ago")
    assert "d" in humanize_since(date(2026, 6, 17), now)
    # > 1 year — picks years-and-days format
    assert "y" in humanize_since(date(2024, 1, 1), now)
