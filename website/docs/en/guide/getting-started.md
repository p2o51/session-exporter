# Getting started

Session Exporter is a small local web app that reads your **Claude Code**, **Codex**, **Cursor**, **Antigravity**, **Pi Agent**, and **Kimi Code** session history, lets you browse and filter it, and exports it — with token and cost accounting.

It runs entirely on your machine. Nothing is uploaded anywhere.

## Requirements

- **Python 3.9+** — that's it. The app uses only the Python standard library, with **zero third-party dependencies**.
- macOS, Linux, or Windows. (Session file locations are detected automatically; see [Data & privacy](/guide/data-sources).)

## Install & run

```bash
git clone https://github.com/p2o51/session-exporter.git
cd session-exporter
python3 app.py
```

Your browser opens at **http://127.0.0.1:8765**. That's the whole install — no build step, no `pip install`.

### Options

```bash
python3 app.py --port 9000     # use a different port
python3 app.py --no-open       # don't auto-open the browser
python3 app.py --host 0.0.0.0  # bind all interfaces (careful — exposes it on your LAN)
```

## First launch

The first launch **indexes** your history. Codex in particular can keep tens of gigabytes of rollout files, so this takes roughly 10 seconds. Session Exporter streams those files rather than loading them whole, so memory stays flat.

The result is cached to `.cache/index.json`, keyed by a fingerprint of your session files — so **subsequent launches are instant**. Whenever your history changes, click **Refresh** in the top bar to re-scan.

## What you'll see

- A **top bar** with total sessions, total tokens, total estimated cost, and a Refresh button.
- A **left sidebar** of filters: search, source, project, and date range.
- A **main table** of sessions with columns for source, project, updated date, message count, tokens, cost, and cache-hit rate.
- Click any row to open a **detail drawer** with the full transcript and a token/cost breakdown.
- Select rows to reveal the **export bar**, and open the **Stats** panel for cost by model and by date.

Next: [Browse & export](/guide/browsing-exporting).
