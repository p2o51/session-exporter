# Tokens & cost

Session Exporter turns the raw usage recorded by each tool into per-session and per-selection **token accounting** and **cost estimates** — with prompt caching handled correctly.

## Token accounting

For every session it aggregates the usage the provider actually recorded:

| Field | Meaning |
| --- | --- |
| **Input** | Prompt tokens billed at the full input rate |
| **Output** | Generated tokens (includes reasoning tokens for OpenAI) |
| **Cache read** | Tokens served from the prompt cache (heavily discounted) |
| **Cache write** | Tokens written to the cache (Claude) |
| **Reasoning** | Thinking / reasoning tokens (Codex) |
| **Cache-hit rate** | `cache_read / (input + cache_write + cache_read)` |

These come straight from the session logs — they are **measured, not estimated** (except for Cursor, see below).

## Token basis

Each session is tagged with how its numbers were obtained:

- **`recorded`** — Claude Code and Codex log real usage per turn. Fully accurate.
- **`context-snapshot`** — Cursor only records the size of the final context window, not cumulative spend or cache activity. A `~` marks these numbers, and **cost is not computed** for them (see [Data & privacy](/guide/data-sources)).

## Cost estimation

Every `recorded` session is priced from its tokens × per-model rates. Caching is billed the way each provider actually bills it:

- **Cache reads** — `0.1×` the input rate.
- **Anthropic cache writes** — `1.25×` for the 5-minute cache, `2×` for the 1-hour cache. Session Exporter reads the 5-min / 1-hour split out of Claude's logs, so the write cost is exact, not approximated.
- **Codex / OpenAI** — the recorded `input` already includes the cached portion, so cost uses `(input − cached) × input_rate + cached × cache_read_rate + output × output_rate`.

Cost shows up as a **Cost** column in the table, a tile in the detail drawer, and a running total on the selection bar and the top bar.

## The Stats panel

Click **Stats** in the toolbar to open a breakdown of the **current filter**:

- **Summary tiles** — sessions, tokens, estimated cost, and cache-hit rate.
- **By model** — a table of every model, its session count, tokens, and cost, with cost bars, sorted most-expensive first.
- **By date** — the same, grouped by day (newest first).

Because it respects the active filter, questions like *"how much did the last 3 days cost?"* or *"how much have I spent on gpt-5.5?"* are one glance: set the date range or source filter, open Stats, read the total.

Rows using an **estimated** rate (a model whose exact price isn't published) are flagged with `~`. Cursor sessions are excluded from cost and shown as `—`.

## Editing prices — `pricing.json`

Prices live in an editable [`pricing.json`](https://github.com/p2o51/session-exporter/blob/main/pricing.json) next to the app. Rates are **USD per 1,000,000 tokens**:

```json
{
  "models": {
    "claude-opus-4-8": {
      "input": 5, "output": 25, "cache_read": 0.5,
      "cache_write_5m": 6.25, "cache_write_1h": 10
    },
    "gpt-5.5": { "input": 5.0, "output": 30.0, "cache_read": 0.5 }
  },
  "aliases": { "openai": "gpt-5.5" }
}
```

- `cache_read` — the discounted cached-input rate.
- `cache_write_5m` / `cache_write_1h` — Anthropic cache-write rates (other providers don't bill cache writes; omit them).
- `aliases` — map a raw model string (e.g. a provider fallback name) to a priced model.
- `"estimated": true` on a model flags it in the UI with `~`.

Model keys are matched **case-insensitively**. A model missing from `pricing.json` is shown as `—` (not priced) rather than guessed — so a dash always means "no price configured", never "free".

Ships with rates filled in: **Claude** from Anthropic's official pricing; **OpenAI, Z.ai (GLM), Moonshot (Kimi)** from their public pricing. Change any number to match your own contract, then hit **↻ Reload prices** in the Stats panel — it applies instantly, without re-scanning your data.
