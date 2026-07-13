---
pageType: home

hero:
  name: Session Exporter
  text: Browse & export your AI coding history
  tagline: Claude Code · Codex · Cursor · Antigravity — one list, with token & cost accounting
  image:
    src: /logo.svg
    alt: Session Exporter
  actions:
    - theme: brand
      text: Get started
      link: /guide/getting-started
    - theme: alt
      text: GitHub
      link: https://github.com/p2o51/session-exporter

features:
  - title: One list, four tools
    details: Browse every Claude Code, Codex, Cursor, and Antigravity session together. Filter by source, project folder, date range, and full-text search. Sort by recency, cost, tokens, or size.
    icon: 🗂️
  - title: Multi-select → ZIP export
    details: Select or select-all (following the active filter), then export a self-contained archive — metadata index plus a machine-readable JSON and a human-readable Markdown transcript per session.
    icon: 📦
  - title: Export for Notion
    details: A CSV + matching Markdown folder that Notion imports as a database — transcript as the page body, metadata as properties, so you rebuild your filters inside Notion.
    icon: 📓
  - title: Token accounting with cache
    details: Real, provider-recorded usage — input / output / cache-read / cache-write / reasoning tokens, plus cache-hit rate, per session and per selection.
    icon: 🔢
  - title: Cost estimation
    details: Every session priced from its tokens × per-model rates (cache reads 0.1×, Anthropic cache writes 1.25×/2×). A Stats panel breaks cost down by model and by date.
    icon: 💰
  - title: Local & private
    details: Reads your local session files directly — nothing leaves your machine. Pure Python 3.9+ standard library, zero dependencies. Cursor and Antigravity databases are opened strictly read-only.
    icon: 🔒
---
