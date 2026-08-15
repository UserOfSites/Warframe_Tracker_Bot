from titania.config import Config
from titania.data.aggregate.source import AggregateSource
from titania.data.cached import CachedDataSource
from titania.data.fake.source import InMemoryFakeSource
from titania.data.fallback import FallbackDataSource
from titania.data.official.source import OfficialWorldStateSource
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

    # Live sources stall occasionally (fissures freeze hours in the past). Back
    # them with DE's official worldstate feed so fissures keep updating even when
    # the primary is down; it flips back automatically once the primary recovers.
    if config.data_source != "fake" and config.fissure_fallback:
        inner = FallbackDataSource(
            inner,
            OfficialWorldStateSource(
                worldstate_url=config.official_worldstate_url,
                solnodes_base_url=config.warframestat_base_url,
            ),
        )

    return CachedDataSource(inner, ttl_seconds=config.fissure_cache_ttl)
