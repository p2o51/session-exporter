# Data & privacy

Session Exporter reads your local session files directly. **Nothing leaves your machine** — there is no account, no telemetry, and no network call except serving the UI to your own browser on `127.0.0.1`.

## Where the data comes from

| Source | Location | Token basis |
| --- | --- | --- |
| **Claude Code** | `~/.claude/projects/<folder>/<uuid>.jsonl` | `recorded` — summed `usage`, including cache create/read |
| **Codex** | `~/.codex/sessions/**/rollout-*.jsonl` (and `archived_sessions/`) | `recorded` — the final `token_count` event (includes cached input & reasoning) |
| **Cursor** | the global SQLite DB `…/Cursor/User/globalStorage/state.vscdb` | `context-snapshot` — see below |
| **Antigravity** | `~/.gemini/antigravity{,-cli}/conversations/*.db` | `recorded` — `gen_metadata` usage (input, cache read, output, reasoning) |
| **Pi Agent** | `~/.pi/agent/sessions/**/*.jsonl` | `recorded` — per-turn `usage` (input, output, cacheRead, cacheWrite) |

### Claude Code

Each project folder holds one JSONL file per session. Token usage is summed from every assistant turn's `usage` object, and the 5-minute / 1-hour cache-write split is read out for accurate cost. The project path comes from the `cwd` recorded in the log.

### Codex

Rollout files can reach hundreds of megabytes. Session Exporter streams them — counting messages at the byte level and JSON-parsing only the head (session metadata, first user message, model) and tail (final token count) — so a 650 MB session lists in well under a second. Message counts on very large sessions are a fast byte-level estimate (±a couple of system turns); every other number is exact.

### Cursor

Cursor stores everything in one large SQLite database. Session Exporter opens it **strictly read-only** (`?mode=ro`, falling back to `?immutable=1`) and only ever does indexed primary-key lookups — it never writes to, locks, or otherwise touches your live Cursor database, even while Cursor is running.

Cursor does not record cumulative token spend or cache activity — only the size of a session's final context window. Session Exporter surfaces that number honestly as `context-snapshot` (marked with `~`) and does **not** compute a cost for it, rather than inventing one.

### Antigravity

Antigravity (IDE and CLI) stores one SQLite database per conversation under `~/.gemini/antigravity/conversations/` and `~/.gemini/antigravity-cli/conversations/`. Session Exporter opens each DB **read-only** (preferring `?immutable=1` so WAL sidecars never block the scan) and decodes the protobuf blobs in `gen_metadata` / `steps` / `trajectory_metadata_blob` with a tiny wire-format reader — no third-party protobuf dependency.

Token totals come from recorded generation metadata (uncached input, cache reads, output text, and reasoning). Workspace paths come from the trajectory metadata. Legacy encrypted `.pb` conversation files are skipped; only the SQLite `.db` format is supported.

### Pi Agent

Pi Agent stores one JSONL file per session under `~/.pi/agent/sessions/<encoded-cwd>/`. Each file opens with a `type:"session"` header (id, cwd, timestamp), then a stream of `message` events. Assistant turns carry recorded `usage` with `input` / `output` / `cacheRead` / `cacheWrite`. Session Exporter sums those fields and renders text, thinking, and toolCall blocks into the transcript.

## The cache

The scan result is written to `.cache/index.json` next to the app, keyed by a fingerprint of your session files (paths + sizes + modification times). If nothing changed, relaunches load from cache instantly. If files changed, or you click **Refresh**, the index is rebuilt. Deleting `.cache/` just forces a fresh scan — it's safe.

Cost is applied to the cached index on every load, so editing `pricing.json` takes effect on the next launch (or immediately via **↻ Reload prices**) without re-parsing your data.

## Adding another source

Each parser is a single file in `parsers/` implementing a small contract — `list_sessions()` and `load_messages()`. Adding another tool is one new file; nothing else in the app needs to know about it.
