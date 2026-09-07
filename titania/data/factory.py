from titania.config import Config
from titania.data.aggregate.source import AggregateSource
from titania.data.cached import CachedDataSource
from titania.data.failover import FailoverDataSource
from titania.data.fake.source import InMemoryFakeSource
from titania.data.official.source import OfficialWorldStateSource
from titania.data.source import WarframeDataSource
from titania.data.warframestat.source import WarframestatSource


def build_data_source(config: Config) -> WarframeDataSource:
    if config.data_source == "fake":
        return CachedDataSource(
            InMemoryFakeSource.from_fixtures(), ttl_seconds=config.fissure_cache_ttl
        )

    if config.data_source == "aggregate":
        primary: tuple[str, WarframeDataSource] = (
            "aggregate", AggregateSource(base_url=config.warframestat_base_url)
        )
    else:
        primary = (
            "warframestat", WarframestatSource(base_url=config.warframestat_base_url)
        )

    # Live upstreams stall/500 from time to time. Behind DE's official worldstate
    # feed, the bot fails over per-read to whichever source is healthy and flips
    # back automatically once the primary recovers — no restart, no single point
    # of failure. FISSURE_FALLBACK=false pins it to the primary only.
    if config.fissure_fallback:
        inner: WarframeDataSource = FailoverDataSource([
            primary,
            ("official", OfficialWorldStateSource(
                worldstate_url=config.official_worldstate_url,
                solnodes_base_url=config.warframestat_base_url,
            )),
        ])
    else:
        inner = primary[1]

    return CachedDataSource(inner, ttl_seconds=config.fissure_cache_ttl)
