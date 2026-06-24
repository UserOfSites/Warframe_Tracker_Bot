from titania.data.fake.source import InMemoryFakeSource
from titania.domain.mission_type import FAST_MISSIONS
from titania.services.fissure_service import FissureService
from titania.services.guild_settings import GuildSettings, static_resolver


def _settings(
    *,
    allowed=FAST_MISSIONS,
    blocked=frozenset(),
    pinned=frozenset(),
    dojoshare=frozenset(),
    locale="en",
) -> GuildSettings:
    return GuildSettings(
        allowed_mission_types=allowed,
        blocked_nodes=blocked,
        pinned_nodes=pinned,
        dojoshare_nodes=dojoshare,
        locale=locale,
    )


async def _board(settings: GuildSettings):
    source = InMemoryFakeSource.from_fixtures()
    service = FissureService(source, static_resolver(settings))
    return await service.board_for_guild(None)


async def test_normal_section_holds_only_fast_non_sp_fissures():
    board = await _board(_settings())
    assert all(not f.is_steel_path for f in board.normal)
    assert all(f.mission_type in FAST_MISSIONS for f in board.normal)
    nodes = {f.node for f in board.normal}
    # From fixture: Hepit Capture (Lith, normal), Oxomoco Exterminate (Neo, normal)
    assert "Hepit" in nodes
    assert "Oxomoco" in nodes


async def test_steel_path_section_holds_only_fast_sp_fissures():
    board = await _board(_settings())
    assert all(f.is_steel_path for f in board.steel_path)
    assert all(f.mission_type in FAST_MISSIONS for f in board.steel_path)
    nodes = {f.node for f in board.steel_path}
    # From fixture: Ukko Capture SP, Acheron Exterminate SP
    assert "Ukko" in nodes
    assert "Acheron" in nodes


async def test_default_filter_drops_slow_mission_types():
    board = await _board(_settings())
    visible = {f.node for f in board.normal} | {f.node for f in board.steel_path}
    # Excavation, Defense, Survival, Interception — none of these nodes should show up
    for slow_node in ("Augustus", "Hydron", "Stephano", "Mot", "Draco"):
        assert slow_node not in visible


async def test_blocked_nodes_remove_from_normal_and_steel_path():
    board = await _board(_settings(blocked=frozenset({"Hepit", "Acheron"})))
    visible = {f.node for f in board.normal} | {f.node for f in board.steel_path}
    assert "Hepit" not in visible
    assert "Acheron" not in visible


async def test_blocked_nodes_match_case_insensitively():
    board = await _board(_settings(blocked=frozenset({"hepit"})))
    visible = {f.node for f in board.normal}
    assert "Hepit" not in visible


async def test_normal_section_sorted_by_era_tier_then_expiry():
    board = await _board(_settings())
    tiers = [f.tier for f in board.normal]
    assert tiers == sorted(tiers)


async def test_dojoshare_promotes_sp_at_listed_node_regardless_of_mission_type():
    board = await _board(_settings(dojoshare=frozenset({"Draco", "Mot", "Stephano"})))
    nodes = {f.node for f in board.dojoshare}
    # From fixture: SP Draco Survival, SP Mot Survival, SP Stephano Defense
    assert {"Draco", "Mot", "Stephano"} <= nodes
    assert all(f.is_steel_path for f in board.dojoshare)


async def test_dojoshare_does_not_promote_normal_difficulty_fissures():
    board = await _board(_settings(dojoshare=frozenset({"Draco"})))
    # Fixture has both SP Draco Survival and normal-difficulty Draco Survival.
    # Only the SP one should show up in dojoshare; the normal one is dropped
    # because Survival is not in the default fast-types filter.
    dojo_nodes = [(f.node, f.is_steel_path) for f in board.dojoshare]
    assert ("Draco", True) in dojo_nodes
    assert ("Draco", False) not in dojo_nodes
    # And the normal Draco Survival should not appear in the Normal section either.
    assert "Draco" not in {f.node for f in board.normal}


async def test_dedup_sp_dojoshare_node_not_duplicated_into_steel_path():
    board = await _board(_settings(dojoshare=frozenset({"Acheron"})))
    # Acheron is SP Exterminate (a fast type). With Acheron in dojoshare it
    # must land in dojoshare only — not duplicated into Steel Path.
    assert "Acheron" in {f.node for f in board.dojoshare}
    assert "Acheron" not in {f.node for f in board.steel_path}


async def test_dojoshare_bypasses_blocked_nodes():
    # Even if Draco is blocked, dojoshare opt-in takes priority.
    board = await _board(
        _settings(
            blocked=frozenset({"Draco"}),
            dojoshare=frozenset({"Draco"}),
        )
    )
    assert "Draco" in {f.node for f in board.dojoshare}


async def test_dojoshare_section_sorted_by_era_tier_then_expiry():
    board = await _board(_settings(dojoshare=frozenset({"Draco", "Mot", "Stephano"})))
    tiers = [f.tier for f in board.dojoshare]
    assert tiers == sorted(tiers)


async def test_next_resets_drawn_from_all_fissures_not_filtered_ones():
    # The filter hides Excavation/Defense/Survival, but the next-reset list
    # must still surface eras represented only by those slow missions.
    board = await _board(_settings())
    # Fixture has SP Stephano Defense (Axi) and SP Hydron Defense (Meso) — even
    # though those are filtered out of Steel Path, they must appear here.
    sp_eras = {r.era for r in board.next_resets if r.is_steel_path}
    from titania.domain.era import Era

    assert Era.AXI in sp_eras  # SP Stephano Defense Axi, SP Acheron Exterminate Axi
    assert Era.MESO in sp_eras  # SP Hydron Defense Meso, SP Ukko Capture Meso


async def test_next_resets_pick_the_soonest_per_combo():
    board = await _board(_settings())
    # Fixture has two Lith entries: normal Hepit Capture (00:30) and normal
    # Draco Survival (00:20). The Normal-Lith reset must pick the 00:20 one.
    from titania.domain.era import Era

    lith_normal = next(
        r for r in board.next_resets if r.era == Era.LITH and not r.is_steel_path
    )
    assert lith_normal.expires_at.minute == 20


async def test_next_resets_sorted_normal_then_sp_then_by_tier():
    board = await _board(_settings())
    keys = [(r.is_steel_path, r.era.value) for r in board.next_resets]
    # All non-SP entries must come before all SP entries.
    first_sp_index = next((i for i, k in enumerate(keys) if k[0]), len(keys))
    assert all(not is_sp for is_sp, _ in keys[:first_sp_index])
    assert all(is_sp for is_sp, _ in keys[first_sp_index:])


async def test_railjack_skirmish_dropped_from_all_sections_and_resets():
    # Fixture contains a Lith Skirmish at Korm's Belt — railjack via mission
    # type. Must not appear in any bucket. Also verify next_resets is computed
    # purely from non-railjack data by cross-checking each reset against the
    # soonest non-railjack fissure for its (era, sp) combo.
    from titania.domain.railjack import is_railjack

    source = InMemoryFakeSource.from_fixtures()
    service = FissureService(source, static_resolver(_settings()))
    board = await service.board_for_guild(None)

    visible = {f.node for f in (board.normal + board.steel_path + board.dojoshare)}
    assert "Korm's Belt" not in visible

    raw = await source.fetch_fissures()
    non_rj = [f for f in raw if not is_railjack(f)]
    for r in board.next_resets:
        candidates = [
            f for f in non_rj if f.era == r.era and f.is_steel_path == r.is_steel_path
        ]
        assert r.expires_at == min(f.expires_at for f in candidates)


async def test_railjack_exterminate_at_proxima_node_dropped_from_normal():
    # Bifrost Echo (Venus) is Venus Proxima — Extermination there is railjack
    # mechanically. Should not appear in Normal even though Extermination is
    # in the default fast-types filter.
    board = await _board(_settings())
    assert "Bifrost Echo" not in {f.node for f in board.normal}


async def test_railjack_volatile_at_dojoshare_neutral_node_not_promoted():
    # Numina (Veil) is railjack via mission type Volatile. Even if a guild
    # explicitly added "Numina" to its dojoshare list, railjack still wins.
    board = await _board(_settings(dojoshare=frozenset({"Numina"})))
    assert "Numina" not in {f.node for f in board.dojoshare}


async def test_requiem_fissure_is_dropped_from_all_sections():
    # Fixture has a Requiem Exterminate at Taveuni (Kuva Fortress) — fast
    # mission type, but Requiem era is useless for relic farming.
    board = await _board(_settings())
    all_nodes = {f.node for f in board.normal + board.steel_path + board.dojoshare}
    assert "Taveuni" not in all_nodes


async def test_requiem_does_not_appear_in_next_resets():
    board = await _board(_settings())
    from titania.domain.era import Era

    assert all(r.era is not Era.REQUIEM for r in board.next_resets)


async def test_requiem_dropped_even_if_user_pins_the_node():
    # Pinning Taveuni shouldn't resurrect a Requiem fissure — the era filter
    # runs before pinning is consulted.
    board = await _board(_settings(pinned=frozenset({"Taveuni"})))
    assert "Taveuni" not in {f.node for f in board.normal}


async def test_pinned_node_bypasses_mission_type_filter_for_normal():
    # Augustus (Mars) Excavation is in the fixture as a normal Lith. Excavation
    # is not a fast type; without a pin, it would be dropped. With the pin, it
    # appears in Normal.
    board_without = await _board(_settings())
    assert "Augustus" not in {f.node for f in board_without.normal}

    board_with = await _board(_settings(pinned=frozenset({"Augustus"})))
    assert "Augustus" in {f.node for f in board_with.normal}


async def test_pinned_node_bypasses_mission_type_filter_for_steel_path():
    # Hydron (Sedna) Defense SP is in the fixture. Defense isn't a fast type;
    # pinning it should surface the SP variant in Steel Path.
    board = await _board(_settings(pinned=frozenset({"Hydron"})))
    sp_nodes = {f.node for f in board.steel_path}
    assert "Hydron" in sp_nodes


async def test_blocked_wins_over_pinned():
    # Defensive: if a node is in both blocked and pinned lists, blocked wins
    # (matches the inline comment in the service).
    board = await _board(
        _settings(blocked=frozenset({"Hepit"}), pinned=frozenset({"Hepit"}))
    )
    assert "Hepit" not in {f.node for f in board.normal + board.steel_path}


async def test_pinning_doesnt_resurrect_railjack_node():
    # Railjack filter runs upstream of the partition; pinning a Proxima node
    # still doesn't bring it back.
    board = await _board(_settings(pinned=frozenset({"Bifrost Echo"})))
    assert "Bifrost Echo" not in {f.node for f in board.normal + board.steel_path}
