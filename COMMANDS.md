# Titania Prime — Command Reference

Every command Titania Prime exposes in Discord, with parameters, examples, and notes on autocomplete behavior. All commands are slash commands (`/...`). Owner-only commands are gated by Discord's **Manage Guild** permission.

## Quick reference

| Command | Who | Purpose |
|---|---|---|
| [`/ping`](#ping) | Everyone | Quick liveness + latency check. |
| [`/fissures`](#fissures) | Everyone | One-shot embed with the three-section fissure board. |
| [`/track <channel>`](#track-channel) | Manage Guild | Post an auto-updating fissure embed in a channel. |
| [`/untrack`](#untrack) | Manage Guild | Stop auto-updating and delete the tracked message. |
| [`/settings fissures types`](#settings-fissures-types) | Manage Guild | Manage which mission types count as "fast". |
| [`/settings fissures blocked-nodes`](#settings-fissures-blocked-nodes) | Manage Guild | Hide specific nodes from Normal + Steel Path. |
| [`/settings fissures pinned-nodes`](#settings-fissures-pinned-nodes) | Manage Guild | Always-show specific nodes regardless of type filter. |
| [`/settings dojoshare`](#settings-dojoshare) | Manage Guild | Manage the Steel-Path-only long-farm node list. |
| [`/settings language`](#settings-language) | Manage Guild | Switch the guild's UI language (en / it). |

---

## `/ping`

Returns the bot's gateway round-trip latency.

- **Parameters**: none
- **Response**: ephemeral message (visible only to you)

**Example**

```
/ping
```

> Pong! `42 ms`

Use this when you're not sure if the bot is connected, or to check responsiveness.

---

## `/fissures`

Posts the full three-section fissure board *once* in the current channel, visible to everyone. Honors all of this guild's filters (mission types, blocked nodes, pinned nodes, dojoshare list) and the guild language.

- **Parameters**: none
- **Response**: a public embed with:
  - **Normal** — fast-clear fissures matching the type filter (non-Steel-Path)
  - **Steel Path** — same, Steel-Path variants
  - **Dojoshare** — Steel-Path-only fissures at curated long-farm nodes
  - **Next resets** — soonest expiry per (era, difficulty), two side-by-side columns
  - Updated footer

**Example**

```
/fissures
```

Use this when you want a snapshot. For a self-updating embed, use [`/track`](#track-channel) instead.

> **Note**: Railjack missions and Requiem fissures are filtered out everywhere — they're not relic-cracking material. This is a behavior gate, not a guild preference.

---

## `/track <channel>`

Posts a fissure embed in the channel you pick and **auto-refreshes it every ~30 seconds** by editing the message in-place. No new messages are spammed in chat.

- **Permission**: Manage Guild
- **Parameters**:
  - `channel` — *text channel* (required). The bot must have **Send Messages** and **Embed Links** in this channel.
- **Side effects**:
  - If a previous tracked message exists for this guild, it's deleted before posting the new one (one tracked message per guild).
  - The bot's refresh loop picks up the new tracked message on the next tick.
  - Settings changes via `/settings ...` propagate to the tracked message within one refresh tick.

**Example**

```
/track channel: #void-fissures
```

> Tracking active fissures in #void-fissures. The embed will refresh every ~30s.

If the bot lacks permission in the chosen channel, you'll get an ephemeral error explaining what's missing — nothing is posted.

---

## `/untrack`

Stops the auto-refresh and deletes the tracked embed.

- **Permission**: Manage Guild
- **Parameters**: none
- **Side effects**: removes the per-guild row from the tracked-channels table.

**Example**

```
/untrack
```

> Tracking stopped.

If there's no active tracking, you'll get *"No tracked channel for this server."*. The refresh loop also auto-untracks silently if the tracked message gets deleted or the bot loses permission.

---

## `/settings fissures types`

Manage which mission types count as "fast" — i.e. which missions appear in the **Normal** and **Steel Path** sections. Default is `Exterminate`, `Sabotage`, `Capture`.

- **Permission**: Manage Guild
- **Parameters**:
  - `action` — one of `show` · `add` · `remove` · `reset`
  - `mission_type` — *optional*, required for `add` / `remove`. Autocompletes from the full `MissionType` enum.

**Examples**

```
/settings fissures types action: show
```
> Allowed mission types: Capture, Exterminate, Sabotage

```
/settings fissures types action: add mission_type: Defense
```
> Updated. Allowed mission types: Capture, Defense, Exterminate, Sabotage

```
/settings fissures types action: remove mission_type: Capture
```
> Updated. Allowed mission types: Defense, Exterminate, Sabotage

```
/settings fissures types action: reset
```
> Reset to defaults: Capture, Exterminate, Sabotage

Note: this filter does **not** apply to the Dojoshare section — that section is driven entirely by the dojoshare node list.

---

## `/settings fissures blocked-nodes`

Hide specific nodes from the **Normal** and **Steel Path** sections, even if their mission type is in your type filter. Useful for muting nodes you find boring or annoying.

- **Permission**: Manage Guild
- **Parameters**:
  - `action` — one of `show` · `block` · `unblock` · `clear`
  - `node` — *optional*, required for `block` / `unblock`. Autocomplete is **action-aware**:
    - `block` → suggests from the full Warframe star-chart catalog (~450 nodes)
    - `unblock` → suggests only the nodes currently in your blocked list

**Examples**

```
/settings fissures blocked-nodes action: show
```
> Blocked nodes: _(empty)_

```
/settings fissures blocked-nodes action: block node: Hepit
```
> Updated. Blocked nodes: Hepit

```
/settings fissures blocked-nodes action: unblock node: Hepit
```
> Updated. Blocked nodes: _(empty)_

```
/settings fissures blocked-nodes action: clear
```
> Blocked-nodes list cleared.

Note: blocked-nodes does **not** affect the Dojoshare section — to remove a node from there, edit the dojoshare list instead.

---

## `/settings fissures pinned-nodes`

The opposite of blocked-nodes: **always show** specific nodes regardless of the mission-type filter. Pinning `Hydron` makes Hydron Defense surface even though Defense isn't in the default fast set.

- **Permission**: Manage Guild
- **Parameters**:
  - `action` — one of `show` · `pin` · `unpin` · `clear`
  - `node` — *optional*, required for `pin` / `unpin`. Autocomplete is **action-aware**:
    - `pin` → full Warframe catalog
    - `unpin` → only the nodes currently pinned in this guild

**Examples**

```
/settings fissures pinned-nodes action: pin node: Hydron
```
> Updated. Pinned nodes: Hydron

```
/settings fissures pinned-nodes action: show
```
> Pinned nodes: Hydron

```
/settings fissures pinned-nodes action: unpin node: Hydron
```
> Updated. Pinned nodes: _(empty)_

Precedence rules (defensive, when both lists touch a node):
- Railjack and Requiem filters run first → pinning a Proxima / Requiem node has no effect.
- Blocked > pinned. If the same node is in both lists, it stays hidden.

---

## `/settings dojoshare`

Manage the **Dojoshare** section's curated node list. Dojoshare is Steel-Path-only by design: only the SP variant of a listed node appears, regardless of mission type. Default list: `Draco, Casta, Nimus, Mot, Ani, Elara, Io, Stephano, Circulus, Yuvarium`.

- **Permission**: Manage Guild
- **Parameters**:
  - `action` — one of `show` · `add` · `remove` · `reset`
  - `node` — *optional*, required for `add` / `remove`. Autocomplete is **action-aware**:
    - `add` → full Warframe catalog
    - `remove` → only the nodes currently on the dojoshare list

**Examples**

```
/settings dojoshare action: show
```
> Dojoshare nodes: Ani, Casta, Circulus, Draco, Elara, Io, Mot, Nimus, Stephano, Yuvarium

```
/settings dojoshare action: add node: Helene
```
> Updated. Dojoshare nodes: Ani, Casta, Circulus, Draco, Elara, Helene, Io, Mot, Nimus, Stephano, Yuvarium

```
/settings dojoshare action: remove node: Helene
```
> Updated. Dojoshare nodes: Ani, Casta, Circulus, Draco, Elara, Io, Mot, Nimus, Stephano, Yuvarium

```
/settings dojoshare action: reset
```
> Reset to defaults: …the default list…

Adding a node to dojoshare also bypasses the blocked-nodes list (dojoshare is an explicit opt-in for a specific Steel-Path long farm).

---

## `/settings language`

Set the language used in the fissure embeds and the time strings ("in 23m" vs. "tra 23m", "expired" vs. "scaduto").

- **Permission**: Manage Guild
- **Parameters**:
  - `lang` — `English` or `Italiano` (select-only, no free text)

**Example**

```
/settings language lang: Italiano
```
> Language set to **Italiano**.

The change shows up on the tracked embed within one refresh tick (~30s). It also affects `/fissures` responses immediately. Settings-command responses themselves remain English in v1.

---

## Notes & gotchas

- **All `/settings ...` responses are ephemeral** — they appear only to you, not in chat. So changing settings never spams the channel.
- **Per-guild scope.** Every setting is per-server. Two servers using the same bot can have completely different filters, locale, and dojoshare lists.
- **Autocomplete is action-aware** for the three node-list commands (`blocked-nodes`, `pinned-nodes`, `dojoshare`). When removing, you only see what's on your list — no scrolling through 450 nodes.
- **Refresh interval** is the `FISSURE_CACHE_TTL` env var (default 30 seconds). Tracked embeds get a fresh render every tick using the latest settings from the database.
- **DMs.** Settings and tracking commands only work inside a server. `/ping` and `/fissures` work in DMs but use the bot-wide defaults since there's no per-guild config.
