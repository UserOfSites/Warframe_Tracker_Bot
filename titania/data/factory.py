from titania.config import Config
from titania.data.aggregate.source import AggregateSource
from titania.data.cached import CachedDataSource
from titania.data.fake.source import InMemoryFakeSource
from titania.data.source import WarframeDataSource
from titania.data.warframestat.source import WarframestatSource


def build_data_source(config: Config) -> WarframeDataSource:
    inner: WarframeDataSource
    if config.data_source == "fake":
        inner = InMemoryFakeSource.from_fixtures()
    elif config.data_source == "aggregate":
        inner = AggregateSource(base_url=config.warframestat_base_url)
    else:
        inner = WarframestatSource(base_url=config.warframestat_base_url)
    return CachedDataSource(inner, ttl_seconds=config.fissure_cache_ttl)
