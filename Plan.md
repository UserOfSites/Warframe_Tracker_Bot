# Titania Prime — Warframe Relic-Cracking Discord Bot

## 1. Goals & Scope

A Discord bot **vertically focused on relic cracking**: it surfaces the Void Fissures that are *worth running* for fast relic cracking and filters out the slow ones. The reference screenshot's layout (era column, mission column, time-remaining column, Steel Path indicators) is the target visual.

### Core idea
Two distinct playstyles, two different lanes:

- **Fast lane (Normal + Steel Path sections)** — quick relic-cracking on short objective missions: **Exterminate**, **Sabotage**, **Capture**. In and out in ~2 minutes. This is the mission-type filter, owner-configurable per guild.
- **Dojoshare lane (Dojoshare section)** — the opposite: **long** missions you sit in to farm resources (Survival, Defense, Disruption, …) on a curated list of well-known farming nodes — **Steel Path only**, since the SP variants are where the real resource/Steel Essence value lives. Dojoshare fissures are explicitly *not* fast and *not* filtered by mission type; they are picked by **node**.

The embed renders the three sections in this order: Normal · Steel Path · Dojoshare.

Filter axes, all owner-configurable per guild:
- **Mission-type filter** — applies to Normal + Steel Path. Default: Exterminate / Sabotage / Capture. Does **not** apply to Dojoshare.
- **Blocked-nodes list** — hides specific nodes from Normal + Steel Path. Does not affect Dojoshare; remove a node from the dojoshare list itself if you don't want it.
- **Dojoshare list** — a per-guild list of node names where a long farm is desirable. The matching **Steel Path** fissure shows up in the Dojoshare section regardless of its mission type. The normal-difficulty fissure at the same node is **not** promoted — it falls through to the standard Normal-section rules, which under the default mission-type filter means it is dropped (none of the default dojoshare nodes are fast-type missions).

Dedup rule: a Steel Path fissure that matches a dojoshare node is shown **only** in the Dojoshare section, not duplicated into Steel Path.

### MVP features
- `/fissures` — three-section list (Normal · Steel Path · Dojoshare), grouped by era, with localized time-to-expiry. Honors all guild filters.
- `/settings fissures types …` — **owner / Manage Guild only** — manage the mission-type filter.
- `/settings fissures blocked-nodes …` — owner-only — manage the blocked-nodes list.
- `/settings dojoshare …` — owner-only — manage the dojoshare node list.
- `/settings language` — owner-only — `it` / `en`.
- Auto-refresh of cached data so embeds always show fresh values.

### Explicitly out of scope (v1)
- Cetus / Vallis / Duviri / sortie / Nightwave / Baro reset timers (the second half of the screenshot) — not relic-related; revisit only if requested.
- Relic drop-table lookup — a `/relic <name>` command is not in scope.
- Account-linked features (inventory, riven valuations).
- Trade / price tracking (warframe.market).

---

## 2. Architectural Overview

```
┌───────────────────────────────────────────────────────────────┐
│                       Discord Layer                           │
│   discord.py Cogs · Slash commands · Embed builders · i18n    │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│                       Service Layer                           │
│         FissureService · GuildSettingsService                 │
│         (caching · filtering · sorting · formatting)          │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼  (Bridge)
┌───────────────────────────────────────────────────────────────┐
│                       Data Layer (Bridge)                     │
│                                                               │
│   Abstraction: WarframeDataSource (Protocol)                  │
│       ├─ Implementor: WarframestatSource                      │
│       ├─ Implementor: OfficialWorldStateSource                │
│       └─ Implementor: InMemoryFakeSource (tests)              │
│                                                               │
│   Adapters: WarframestatAdapter · WorldStateAdapter           │
│             (normalize raw JSON → domain models)              │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│   External: api.warframestat.us · content.warframe.com        │
└───────────────────────────────────────────────────────────────┘
```

### Why Bridge here
Two axes vary independently:
- **Where data comes from** (warframestat REST, official `worldState.php`, a stub for tests, possibly a Redis-cached mirror later).
- **How the bot uses the data** (current scope is fissures; extensions stay isolated from the data layer).

The Bridge keeps services unaware of source identity; sources are hot-swappable per environment (e.g. fake source in CI). Each source ships with its own **Adapter** that maps the raw upstream payload to the shared domain model — that is where formats diverge, so that is where the normalization lives.

The filter (fast-only vs. all missions) lives in the **service layer**, not in the data layer — sources always fetch the complete fissure list so the cache is shared across guilds with different filter settings.

---

## 3. Domain Model

All domain types live in `titania/domain/` as `@dataclass(frozen=True)` with no I/O dependencies.

```python
class Era(StrEnum):
    LITH = "Lith"
    MESO = "Meso"
    NEO  = "Neo"
    AXI  = "Axi"
    REQUIEM = "Requiem"
    OMNIA = "Omnia"

class MissionType(StrEnum):
    EXTERMINATE = "Exterminate"
    SABOTAGE    = "Sabotage"
    CAPTURE     = "Capture"
    DEFENSE     = "Defense"
    SURVIVAL    = "Survival"
    EXCAVATION  = "Excavation"
    INTERCEPTION = "Interception"
    DISRUPTION  = "Disruption"
    MOBILE_DEFENSE = "Mobile Defense"
    HIJACK      = "Hijack"
    SPY         = "Spy"
    RESCUE      = "Rescue"
    # ...

# Spy and Rescue are intentionally excluded — short but objective-gated.
FAST_MISSIONS: frozenset[MissionType] = frozenset({
    MissionType.EXTERMINATE,
    MissionType.SABOTAGE,
    MissionType.CAPTURE,
})

# Curated default list of nodes good for Steel Path long resource farms.
# Dojoshare only applies to Steel Path variants of these nodes; the normal-
# difficulty fissure at the same node follows the regular Normal-section rules.
# Owners can override this per-guild.
DEFAULT_DOJOSHARE_NODES: frozenset[str] = frozenset({
    # Ceres
    "Draco",        # Survival
    "Casta",        # Defense
    # Eris
    "Nimus",        # Survival
    # Void
    "Mot",          # Survival
    "Ani",          # Defense
    # Jupiter
    "Elara",        # Survival
    "Io",           # Defense
    # Uranus
    "Stephano",     # Defense
    # Lua
    "Circulus",     # Omnia Survival
    "Yuvarium",     # Omnia Survival
})

@dataclass(frozen=True)
class Fissure:
    era: Era
    mission_type: MissionType
    node: str              # "Augustus"
    planet: str            # "Mars"
    expires_at: datetime   # UTC
    is_steel_path: bool
    is_hard: bool          # storm fissure / requiem etc.
    tier: int              # 1..5 for sorting

@dataclass(frozen=True)
class FissureBoard:
    """What `/fissures` renders — three sections from the same source data."""
    normal: list[Fissure]      # fast-type, not SP
    steel_path: list[Fissure]  # fast-type, SP, not dojoshare
    dojoshare: list[Fissure]   # SP only, node in dojoshare list, any mission type
    generated_at: datetime
```

---

## 4. Data Layer (Bridge Pattern)

### 4.1 Abstraction
```python
# titania/data/source.py
class WarframeDataSource(Protocol):
    async def fetch_fissures(self) -> list[Fissure]: ...
```

Sources always return the **unfiltered** list — filtering is a per-guild concern handled above. Both normal and Steel Path fissures are returned in the same list; `Fissure.is_steel_path` distinguishes them.

### 4.2 Implementors
| Implementor | Endpoint / origin | Notes |
|---|---|---|
| `WarframestatSource` | `https://api.warframestat.us/pc/fissures` | Primary; narrow JSON endpoint with friendly fields. |
| `AggregateSource` | `https://api.warframestat.us/pc` | Built in Phase 6 to prove the Bridge by swap. DE retired `content.warframe.com/dynamic/worldState.php` so `OfficialWorldStateSource` isn't viable today; this aggregate-endpoint source plays the same role (different URL, different orchestration, same Protocol). |
| `InMemoryFakeSource` | Static fixtures | Drives tests and local dev without network. |

Each implementor owns its **HTTP client** (a shared `httpx.AsyncClient` injected via constructor), its **error handling**, and its **adapter**.

### 4.3 Adapters
Adapters are pure functions: `raw_json -> domain.Fissure`. They live next to their source:
- `WarframestatFissureAdapter` — handles fields like `tier`, `isHard`, `eta`, `missionType`.
- `WorldStateFissureAdapter` — resolves `Modifier` → `Era`, `Node` → `(node_name, planet)`, `MissionType` enum via the Public Export.

Pure adapters are trivially unit-testable from captured JSON fixtures.

### 4.4 Composition root
A factory selects the source from config:

```python
def build_data_source(cfg: Config) -> WarframeDataSource:
    match cfg.data_source:
        case "warframestat":   return WarframestatSource(http=...)
        case "official":       return OfficialWorldStateSource(http=...)
        case "fake":           return InMemoryFakeSource.from_fixtures()
```

---

## 5. Service Layer

### 5.1 Caching wrapper
A `CachedDataSource` decorator wraps any `WarframeDataSource`:
- Fissures: TTL ~30 s (they tick and rotate fast).

Cache is in-memory (`cachetools.TTLCache`); Redis is a v2 concern. The cache is **global**, not per-guild — filtering happens after the cache read.

### 5.2 Services

**`FissureService`**
- `board_for_guild(guild_id) -> FissureBoard`
  1. Pull the full fissure list from the cached source.
  2. Load the guild's settings: `allowed_mission_types`, `blocked_nodes`, `dojoshare_nodes`.
  3. **Partition** the list into three buckets in a single pass, in this priority order (first match wins):
     - **Dojoshare** — `is_steel_path AND node in dojoshare_nodes`. Bypasses mission-type and blocked-node filters; node-presence on the Steel Path variant is the explicit opt-in. Normal-difficulty fissures at dojoshare nodes are **not** matched here.
     - **Steel Path** — `is_steel_path AND mission_type in allowed_mission_types AND node not in blocked_nodes`.
     - **Normal** — `not is_steel_path AND mission_type in allowed_mission_types AND node not in blocked_nodes`.
     - Otherwise: dropped.
  4. Sort each bucket by era tier, then expiry.
  5. Return a `FissureBoard`.

  Single-pass partition (not three filters) avoids double-counting and makes the dedup rule explicit in code. The SP-only dojoshare gate means a normal-difficulty fissure at Draco (Interception) is dropped under default settings — exactly as intended, since you wouldn't run normal Draco for dojoshare anyway.

**`GuildSettingsService`**
- CRUD for `(guild_id, locale, allowed_mission_types, blocked_nodes, dojoshare_nodes)`.
- Enforces the **owner / Manage Guild permission check** at the command boundary — the service itself accepts a pre-authorized caller and just writes.
- Validates inputs: mission types against the `MissionType` enum; node names against a canonical node set sourced from the data layer (rejects typos like `"Drako"` early).

### 5.3 Refresh scheduler
A single background task (`asyncio.create_task`) refreshes the fissure cache every 30 s so command responses are always sub-100 ms.

---

## 6. Discord Layer

### 6.1 Framework
`discord.py` 2.x with **application commands** (slash). One `Cog` per command family:
- `cogs/fissures.py`
- `cogs/settings.py`

### 6.2 Commands

Slash-command groups (`/settings` uses subcommand groups for ergonomics):

| Command | Who | Behavior |
|---|---|---|
| `/fissures` | Everyone | Shows the three-section board (Normal · Steel Path · Dojoshare) for the guild. |
| `/settings fissures types <show \| add \| remove \| reset>` | **Owner / Manage Guild** | Manage `allowed_mission_types`. `reset` → fast trio. |
| `/settings fissures blocked-nodes <show \| block \| unblock \| clear>` | **Owner / Manage Guild** | Manage `blocked_nodes` (applies to Normal + Steel Path only). |
| `/settings dojoshare <show \| add \| remove \| reset>` | **Owner / Manage Guild** | Manage `dojoshare_nodes`. `reset` → `DEFAULT_DOJOSHARE_NODES`. |
| `/settings language <it\|en>` | **Owner / Manage Guild** | Per-guild locale. |

Permission gate uses `app_commands.default_permissions(manage_guild=True)` so the commands are invisible to non-managers in Discord's UI, plus an in-handler check as defense-in-depth.

Autocomplete:
- `<mission_type>` autocompletes against `MissionType` values, filtered by what's not already in the list.
- `<node>` autocompletes against the canonical Warframe node list (sourced from the data layer), so owners don't have to remember exact spellings.

### 6.3 Embed builders
A dedicated `presentation/` package converts domain objects to `discord.Embed`. The fissure embed mimics the screenshot:
- Three aligned columns rendered as a code block (monospaced) — Discord embed fields wrap unpredictably; a fenced code block gives the table look reliably.
- Era icons via custom emoji (uploaded to the bot's application emoji bucket): `:lith:`, `:neo:`, `:axi:`, `:steel_path:` etc.
- **Three clearly separated blocks**, in this order: **Normal** → **Steel Path** → **Dojoshare**. Same column layout in each. Steel Path rows prefix the era cell with the steel-path emoji as in the screenshot; every row in the Dojoshare block is Steel Path by construction, so the SP prefix shows on all of them. Dojoshare gets a distinct header (`:dojoshare:` emoji or 🏛️ as a placeholder) so players know why those rows are pinned regardless of mission type.
- Empty sections render a short hint instead of nothing — e.g. "No fast Normal fissures right now." — so users don't think the bot is broken.

### 6.4 i18n
- `babel` for plural rules + relative time formatting (`format_timedelta(td, locale="it")` → `"tra 23 minuti"`, `"in un'ora"`).
- String catalog as plain `dict[str, dict[str, str]]` in `i18n/{en,it}.toml` — small surface area, no `.po` toolchain needed yet.
- Per-guild locale stored in SQLite; default `en`.

---

## 7. Storage

SQLite via `aiosqlite`, single file.

```sql
CREATE TABLE guild_settings (
    guild_id              INTEGER PRIMARY KEY,
    locale                TEXT    NOT NULL DEFAULT 'en',
    allowed_mission_types TEXT    NOT NULL DEFAULT 'Exterminate,Sabotage,Capture',
    blocked_nodes         TEXT    NOT NULL DEFAULT '',
    dojoshare_nodes       TEXT    NOT NULL DEFAULT 'Draco,Casta,Nimus,Mot,Ani,Elara,Io,Stephano,Circulus,Yuvarium',
    updated_at            TEXT    NOT NULL  -- ISO-8601 UTC
);
```

All three list columns (`allowed_mission_types`, `blocked_nodes`, `dojoshare_nodes`) are comma-joined values — small, readable, no join tables needed for v1. Empty string = empty list. Node names are stored case-preserved but compared case-insensitively in the service layer.

---

## 8. Project Layout

```
Titania_Prime/
├── Plan.md
├── pyproject.toml
├── README.md
├── .env.example
├── titania/
│   ├── __main__.py           # bot entrypoint
│   ├── config.py             # pydantic-settings, env-driven
│   ├── bot.py                # discord.Client + cog loader
│   │
│   ├── domain/
│   │   ├── era.py
│   │   ├── mission_type.py   # incl. FAST_MISSIONS constant
│   │   └── fissure.py        # Fissure + FissureBoard
│   │
│   ├── data/
│   │   ├── source.py         # Protocol (abstraction)
│   │   ├── cached.py         # TTL decorator
│   │   ├── factory.py
│   │   ├── warframestat/
│   │   │   ├── source.py
│   │   │   └── adapters.py
│   │   ├── worldstate/
│   │   │   ├── source.py
│   │   │   ├── adapters.py
│   │   │   └── public_export.py   # item-path → name lookup
│   │   └── fake/
│   │       ├── source.py
│   │       └── fixtures/*.json
│   │
│   ├── services/
│   │   ├── fissure_service.py
│   │   └── guild_settings_service.py
│   │
│   ├── presentation/
│   │   ├── embeds.py
│   │   ├── tables.py         # monospaced column layout helper
│   │   └── emoji.py
│   │
│   ├── i18n/
│   │   ├── translator.py
│   │   ├── en.toml
│   │   └── it.toml
│   │
│   ├── cogs/
│   │   ├── fissures.py
│   │   └── settings.py
│   │
│   └── storage/
│       ├── db.py             # aiosqlite connection mgmt
│       └── guild_settings.py # repository
│
└── tests/
    ├── unit/
    │   ├── adapters/         # adapter tests from JSON fixtures
    │   ├── services/         # incl. filter + SP-split behavior tests
    │   └── presentation/
    └── integration/
        └── test_fake_source_flow.py
```

---

## 9. Configuration

`pydantic-settings`, env-driven (`.env` for local, real env vars in production):

| Var | Default | Purpose |
|---|---|---|
| `DISCORD_TOKEN` | — | Bot token (required). |
| `DATA_SOURCE` | `warframestat` | `warframestat` / `aggregate` / `fake`. |
| `WARFRAMESTAT_BASE_URL` | `https://api.warframestat.us` | Override for self-hosted mirror. |
| `FISSURE_CACHE_TTL` | `30` | Seconds. |
| `DEFAULT_LOCALE` | `en` | Fallback when a guild has no preference. |
| `DEFAULT_FAST_MISSIONS` | `Exterminate,Sabotage,Capture` | Bot-wide default; per-guild can override. |
| `DEFAULT_DOJOSHARE_NODES` | `Draco,Casta,Nimus,Mot,Ani,Elara,Io,Stephano,Circulus,Yuvarium` | Bot-wide default dojoshare list (SP-only). Per-guild can override. |
| `DB_PATH` | `./titania.db` | SQLite file for guild settings. |
| `LOG_LEVEL` | `INFO` | |

---

## 10. Dependencies (proposed)

```toml
[project]
dependencies = [
    "discord.py>=2.4",
    "httpx>=0.27",
    "pydantic-settings>=2.4",
    "babel>=2.16",          # i18n + relative time formatting
    "cachetools>=5.5",
    "aiosqlite>=0.20",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "respx", "ruff", "mypy"]
```

---

## 11. Testing Strategy

- **Adapter unit tests** — load a captured JSON fixture, run the adapter, assert the resulting domain object. Catches upstream schema drift.
- **Service tests** — inject `InMemoryFakeSource`, assert the partition rules:
  - default mission-type filter hides Defense / Survival / Excavation / Spy / Rescue from Normal + Steel Path
  - blocked-nodes list removes specific nodes from Normal + Steel Path but **not** from Dojoshare
  - dojoshare list pulls an **SP** node into the Dojoshare section even when its mission type is not in the type filter (e.g. SP Draco Survival appears under default config though Survival is not a fast type)
  - **normal-difficulty fissure at a dojoshare node is NOT promoted** — e.g. normal Draco Survival is dropped (Survival not fast, SP gate prevents dojoshare promotion); the standard Normal-section rules apply unchanged
  - dedup: an SP fissure matching a dojoshare node appears only in Dojoshare, never duplicated into Steel Path
  - SP fissure at a non-dojoshare fast-type node (e.g. SP Hepit Capture) lands in Steel Path, not Dojoshare
  - empty section produces the right "nothing matches" hint
- **Presentation tests** — snapshot the rendered table string per locale, covering all combinations of empty/non-empty sections (three sections × two locales).
- **HTTP layer** — `respx` to mock `httpx` responses without hitting the network.
- **No live network in CI** — `DATA_SOURCE=fake` is the default test config.

---

## 12. Deployment

- **v1**: Single container (Docker), `python -m titania`, run on Fly.io / Railway / a small VPS. SQLite on a mounted volume.
- **Health**: `GET /healthz` exposed via a tiny `aiohttp` server for the platform's healthcheck.
- **Observability**: structured logs (`structlog`) to stdout; metrics deferred to v2.

---

## 13. Roadmap

| Phase | Deliverable |
|---|---|
| **0 — Skeleton** | Project layout, config, empty bot that connects and responds to `/ping`. |
| **1 — Data layer** | Domain models + `WarframestatSource` + adapter + fake source + tests. |
| **2 — Fissures (filtered)** | `FissureService` partition with mission-type filter, embed with Normal + Steel Path sections, English only. |
| **3 — Dojoshare lane** | `DEFAULT_DOJOSHARE_NODES`, third section in `FissureBoard` and the embed, dedup rule. |
| **4 — Settings** | SQLite storage with all three list columns, `/settings fissures types`, `/settings fissures blocked-nodes`, `/settings dojoshare`, `/settings language` (all owner-gated), node-name autocomplete. |
| **5 — i18n** | Babel relative-time, Italian catalog, `/settings language`. |
| **6 — Second source** | `OfficialWorldStateSource` + adapter, prove the Bridge by switching via env. |
| **7 — Polish** | Auto-refresh scheduler, Docker image, deploy. |

---

## 14. Open Questions

1. **Custom emoji** — does the bot ship with its own application-level emoji (Discord supports up to 2000 per app since 2024), or rely on per-guild uploads? Application-level is cleaner; flagging for confirmation.
2. **Settings response localization** — the embed and `/fissures` output are localized (en/it). The `/settings ...` command responses are currently English-only. Localize next time someone touches that cog.

## 15. Resolved (during build)

- **Node-name validation source** — picked `https://api.warframestat.us/solnodes`. Returns `SolNode*` keys for regular nodes and `CrewBattleNode*` for Railjack — same source we use to maintain `RAILJACK_NODES`.
- **Time formatting** — went with locale-specific TOML templates (`"in {h}h {m:02d}m"` / `"tra {h}h {m:02d}m"`) instead of Babel's `format_timedelta`, because Babel drops minute precision for durations ≥ 1 hour ("in 1 hour" instead of "in 1h 23m"), which is wrong for fissures where minute granularity matters. Babel stays as an option for future plural rules.
- **Official world-state endpoint** — `content.warframe.com/dynamic/worldState.php` is no longer publicly served (returns 404). Phase 6 pivoted to `AggregateSource` against warframestat's aggregate `/pc` endpoint to prove the Bridge with genuinely different orchestration. If DE republishes worldState.php, dropping in a real implementation is a one-file change.
- **`/fissures all:true` override** — dropped. Configuration through `/settings` is enough; the escape hatch added complexity without a real use case.
