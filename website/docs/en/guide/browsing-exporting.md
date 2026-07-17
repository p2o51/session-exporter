# Browse & export

## Browsing & filtering

Every session from all six tools appears in one list. The left sidebar drives what's shown:

- **Search** — matches the title, project, and model.
- **Source** — toggle Claude Code / Codex / Cursor / Antigravity / Pi Agent / Kimi Code on and off (each chip shows its session count).
- **Project** — the folder a session belongs to. The list is searchable and ordered by session count.
- **Date range** — a from/to filter on the session's updated date.

Sort the table by **Recently updated**, **Recently created**, **Most expensive**, **Most tokens**, **Most messages**, or **Title A–Z**.

The top-right counter shows how many of your total sessions match the current filter, along with their combined tokens and cost.

## Reading a session

Click a row to open the detail drawer. It shows:

- The title, source, project path, model, message count, and date range.
- A **token grid**: total / input / output, plus cache read, cache write, and reasoning where the source records them, and the **cache-hit rate**.
- The **estimated cost** for that session.
- The full **transcript**, with each turn colour-coded by role (user, assistant, reasoning, system) and timestamped. Very long transcripts render the first 500 messages; export to get the complete text.

## Selecting

- Tick a row's checkbox to select it. Selection **persists across filters** — narrow the list, select more, widen it again, and your earlier picks are still selected.
- **Select all** selects every session in the *current filter*. Untick it (or use **Clear**) to reset.

When anything is selected, a bar appears at the bottom showing the count, combined tokens, cost, and cache-hit rate, with two export buttons.

## Export ZIP

**Export ZIP** produces a self-contained archive of the selected sessions:

```
sessions-export.zip
├── index.json          # metadata for every session, plus the filter you used
├── index.csv           # the same metadata as a flat table
├── README.txt
└── sessions/
    ├── <source>__<id>.json   # full metadata + transcript (machine-readable)
    └── <source>__<id>.md     # the same transcript, human-readable
```

`index.json` and `index.csv` carry all the metadata columns — source, project, dates, model, message count, every token count, cache-hit rate, and **cost** — so the export is a complete, portable record of what you selected.

## Export for Notion

**Export for Notion** produces a differently-shaped archive designed for Notion's importer — see [Export to Notion](/guide/notion) for the full walkthrough.

## Re-scanning

The index is cached for speed. If you've had new sessions since launch, click **Refresh** in the top bar to re-scan your session files. (Editing prices only? Use **↻ Reload prices** in the Stats panel instead — it's instant and doesn't re-scan.)
