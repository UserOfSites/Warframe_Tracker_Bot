from titania.data.fake.source import InMemoryFakeSource


async def test_fake_source_loads_fixtures_and_skips_expired():
    src = InMemoryFakeSource.from_fixtures()
    fissures = await src.fetch_fissures()
    # The fixture has 15 entries; one is `expired: true`, so 14 survive.
    assert len(fissures) == 14
    assert all(f.expires_at.tzinfo is not None for f in fissures)


async def test_fake_source_returns_copy_not_internal_list():
    src = InMemoryFakeSource.from_fixtures()
    first = await src.fetch_fissures()
    first.clear()
    second = await src.fetch_fissures()
    assert len(second) > 0
