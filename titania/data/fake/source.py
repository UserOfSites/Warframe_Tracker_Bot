import json
from importlib import resources

from titania.data.warframestat.adapters import adapt_fissures
from titania.domain.fissure import Fissure


class InMemoryFakeSource:
    """WarframeDataSource backed by a static JSON fixture — no network.

    The fixture uses the warframestat schema so the same adapter applies and we
    exercise it in tests.
    """

    def __init__(self, fissures: list[Fissure]) -> None:
        self._fissures = fissures

    @classmethod
    def from_fixtures(cls) -> "InMemoryFakeSource":
        raw = (
            resources.files("titania.data.fake.fixtures")
            .joinpath("fissures.json")
            .read_text(encoding="utf-8")
        )
        return cls(adapt_fissures(json.loads(raw)))

    async def fetch_fissures(self) -> list[Fissure]:
        return list(self._fissures)

    async def fetch_void_trader(self) -> dict:
        # Static fixture; tests that need an "arrived" Baro can pass their own
        # state directly to BaroService instead of going through this source.
        return {
            "character": "Baro Ki'Teer",
            "location": "Orcus Relay (Pluto)",
            "activation": "2099-01-08T13:00:00.000Z",
            "expiry": "2099-01-10T13:00:00.000Z",
            "inventory": [],
        }

    async def fetch_node_catalog(self) -> frozenset[str]:
        # Tests + local dev: a small but realistic stand-in. Returns the union
        # of nodes referenced by the fixture, the default dojoshare list, and a
        # handful of common dropdown options.
        from titania.domain.mission_type import DEFAULT_DOJOSHARE_NODES

        nodes = {f.node for f in self._fissures}
        nodes |= set(DEFAULT_DOJOSHARE_NODES)
        nodes |= {"Hepit", "Ukko", "Acheron", "Augustus", "Adaro", "Hydron", "Helene"}
        return frozenset(nodes)

    async def aclose(self) -> None:
        return None

    async def __aenter__(self) -> "InMemoryFakeSource":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None
