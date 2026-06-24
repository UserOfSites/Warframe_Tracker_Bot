# Titania Prime

A Discord bot vertically focused on Warframe **relic cracking**: surfaces the Void Fissures worth running for relic farming, filters out the slow ones, and auto-updates a posted embed in a channel of your choice.

See [Plan.md](Plan.md) for the full architecture and design rationale. See [COMMANDS.md](COMMANDS.md) for the complete command reference with examples.

## What it does

- `/fissures` — on-demand three-section board:
  - **Normal** — fast-clear missions (Exterminate / Sabotage / Capture by default)
  - **Steel Path** — same filter, SP variants
  - **Dojoshare** — Steel-Path-only fissures at curated long-farm nodes (Draco, Mot, Stephano, …) regardless of mission type
  - **Next resets** — per-era countdowns for both difficulties
- `/track #channel` — post the embed and have the bot auto-refresh it every ~30s.
- `/untrack` — stop tracking.
- `/settings ...` — per-guild config (Manage Guild required):
  - `fissures types` — which mission types count as "fast"
  - `fissures blocked-nodes` — hide specific nodes
  - `dojoshare` — manage the dojoshare node list
  - `language` — `en` or `it`
- Railjack missions are excluded everywhere.
- Two data sources, swap via `DATA_SOURCE` env var:
  - `warframestat` (default) — `https://api.warframestat.us/pc/fissures`
  - `aggregate` — `https://api.warframestat.us/pc` (full world state, fissures extracted)

## Quick start (local, no Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# Edit .env and put your DISCORD_TOKEN

python -m titania
```

## Quick start (Docker)

```bash
cp .env.example .env
# Edit .env with your DISCORD_TOKEN

docker compose up --build -d
docker compose logs -f
```

SQLite data lives in the `titania-data` named volume. To wipe state:

```bash
docker compose down -v
```

## Configuration

All knobs are env vars (see [.env.example](.env.example)):

| Var | Default | Purpose |
|---|---|---|
| `DISCORD_TOKEN` | — | Bot token (required). |
| `DATA_SOURCE` | `warframestat` | `warframestat` / `aggregate` / `fake`. |
| `WARFRAMESTAT_BASE_URL` | `https://api.warframestat.us` | Override for self-hosted mirror. |
| `FISSURE_CACHE_TTL` | `30` | Cache TTL in seconds. Also the refresh interval for tracked channels. |
| `DEFAULT_LOCALE` | `en` | Fallback locale for guilds that haven't set one. |
| `DEFAULT_FAST_MISSIONS` | `Exterminate,Sabotage,Capture` | Bot-wide default mission-type filter. |
| `DEFAULT_DOJOSHARE_NODES` | `Draco,Casta,...` | Bot-wide default dojoshare list. |
| `DB_PATH` | `./titania.db` (or `/data/titania.db` in Docker) | SQLite file. |
| `LOG_LEVEL` | `INFO` | |

## Required Discord permissions

When creating the bot's invite URL, grant these in the OAuth2 scopes selector:

- **Scopes**: `bot`, `applications.commands`
- **Bot permissions**: `Send Messages`, `Embed Links`, `Use Slash Commands`, `Read Message History` (the last is needed to fetch and edit tracked messages).

## Tests

```bash
pytest -q
```

76 tests as of last commit. The fake data source is the default in tests — no network needed.