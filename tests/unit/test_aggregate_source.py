import httpx
import pytest
import respx

from titania.data.aggregate.source import AggregateSource

_FIXTURE = {
    "fissures": [
        {
            "node": "Hepit (Void)",
            "tier": "Lith",
            "tierNum": 1,
            "missionType": "Capture",
            "expiry": "2099-01-01T00:30:00Z",
            "isHard": False,
            "isStorm": False,
            "expired": False,
        },
        {
            "node": "Acheron (Pluto)",
            "tier": "Axi",
            "tierNum": 4,
            "missionType": "Extermination",
            "expiry": "2099-01-01T00:17:00Z",
            "isHard": True,
            "isStorm": False,
            "expired": False,
        },
    ]
}

_SOLNODES_FIXTURE = {
    "SolNode1": {"value": "Hepit (Void)", "enemy": "Orokin", "type": "Capture"},
    "SolNode2": {"value": "Acheron (Pluto)", "enemy": "Corpus", "type": "Extermination"},
    "CrewBattleNode1": {"value": "Calabash (Veil)", "enemy": "Corpus", "type": "Extermination"},
}


@pytest.fixture
def respx_mock():
    with respx.mock(base_url="https://api.warframestat.us") as r:
        yield r


async def test_aggregate_source_extracts_fissures_from_nested_field(respx_mock):
    respx_mock.get("/pc").mock(return_value=httpx.Response(200, json=_FIXTURE))
    async with AggregateSource() as src:
        fissures = await src.fetch_fissures()
    assert len(fissures) == 2
    nodes = {f.node for f in fissures}
    assert nodes == {"Hepit", "Acheron"}


async def test_aggregate_source_returns_empty_when_field_missing(respx_mock):
    respx_mock.get("/pc").mock(return_value=httpx.Response(200, json={}))
    async with AggregateSource() as src:
        fissures = await src.fetch_fissures()
    assert fissures == []


async def test_aggregate_source_node_catalog_excludes_railjack(respx_mock):
    respx_mock.get("/solnodes").mock(return_value=httpx.Response(200, json=_SOLNODES_FIXTURE))
    async with AggregateSource() as src:
        nodes = await src.fetch_node_catalog()
    assert nodes == frozenset({"Hepit", "Acheron"})
