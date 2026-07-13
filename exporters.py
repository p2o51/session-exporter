"""Build the two export archives.

raw ZIP     — a self-contained dump: index.json + index.csv + per-session .json and .md.
notion ZIP  — the shape Notion's "Import → CSV/Markdown" understands: a top-level
              Sessions.csv plus a Sessions/ folder whose <Name>.md files match the
              CSV's first (title) column, so each row imports with its transcript as
              the page body and the metadata as database properties.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import datetime, timezone

SOURCE_LABEL = {
    "claude": "Claude Code",
    "codex": "Codex",
    "cursor": "Cursor",
    "antigravity": "Antigravity",
}


# ── formatting helpers ───────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def human_tokens(n: int) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _pct(x) -> str:
    return "" if x is None else f"{round(x * 100, 1)}%"


def _date_only(iso: str | None) -> str:
    return (iso or "")[:10]


def _safe_name(name: str, used: set[str]) -> str:
    """Filesystem- and Notion-safe title, unique within the archive."""
    base = re.sub(r"[\\/:*?\"<>|\n\r\t]+", " ", name or "Untitled").strip()
    base = re.sub(r"\s+", " ", base)[:100].strip() or "Untitled"
    candidate = base
    i = 2
    while candidate.lower() in used:
        suffix = f" ({i})"
        candidate = base[: 100 - len(suffix)] + suffix
        i += 1
    used.add(candidate.lower())
    return candidate


# ── transcript rendering ─────────────────────────────────────────────────────

_ROLE_HEADING = {
    "user": "🧑 User",
    "assistant": "🤖 Assistant",
    "system": "⚙️ System",
    "tool": "🔧 Tool",
    "reasoning": "💭 Reasoning",
}


def render_markdown(meta: dict, messages: list[dict]) -> str:
    t = meta.get("tokens") or {}
    lines = [
        f"# {meta.get('title') or 'Untitled session'}",
        "",
        f"- **Source:** {SOURCE_LABEL.get(meta.get('source'), meta.get('source'))}",
        f"- **Project:** {meta.get('project') or '—'}  \n  `{meta.get('project_path') or ''}`",
        f"- **Created:** {meta.get('created_at') or '—'}",
        f"- **Updated:** {meta.get('updated_at') or '—'}",
        f"- **Model:** {meta.get('model') or '—'}",
        f"- **Messages:** {meta.get('message_count', 0)}",
        f"- **Tokens:** {human_tokens(t.get('total'))} total "
        f"(in {human_tokens(t.get('input'))} · out {human_tokens(t.get('output'))}"
        + (f" · cache read {human_tokens(t.get('cache_read'))}" if t.get("cache_read") else "")
        + (f" · reasoning {human_tokens(t.get('reasoning'))}" if t.get("reasoning") else "")
        + f") · basis: {t.get('basis', 'recorded')}",
    ]
    if t.get("cache_hit_rate") is not None:
        lines.append(f"- **Cache hit rate:** {_pct(t.get('cache_hit_rate'))}")
    cost = meta.get("cost_usd")
    if cost is not None:
        lines.append(f"- **Estimated cost:** ${float(cost):,.4f}"
                     + (" *(estimated rate)*" if meta.get("cost_estimated") else ""))
    lines += ["", "---", ""]

    for m in messages:
        heading = _ROLE_HEADING.get(m.get("role"), (m.get("role") or "message").title())
        ts = m.get("ts")
        stamp = f"  ·  *{ts}*" if ts else ""
        lines.append(f"### {heading}{stamp}")
        lines.append("")
        text = (m.get("text") or "").rstrip()
        lines.append(text if text else "*(no text)*")
        lines.append("")
    return "\n".join(lines)


# ── CSV columns (shared shape for both exports) ──────────────────────────────

CSV_HEADER = [
    "Name", "Source", "Project", "Project Path", "Created", "Updated", "Model",
    "Messages", "Total Tokens", "Input Tokens", "Output Tokens",
    "Cache Read Tokens", "Reasoning Tokens", "Cache Hit Rate",
    "Cost (USD)", "Cost Estimated", "Token Basis", "Session ID",
]


def _csv_row(name: str, meta: dict) -> list:
    t = meta.get("tokens") or {}
    cost = meta.get("cost_usd")
    return [
        name,
        SOURCE_LABEL.get(meta.get("source"), meta.get("source")),
        meta.get("project") or "",
        meta.get("project_path") or "",
        _date_only(meta.get("created_at")),
        _date_only(meta.get("updated_at")),
        meta.get("model") or "",
        meta.get("message_count", 0),
        int(t.get("total") or 0),
        int(t.get("input") or 0),
        int(t.get("output") or 0),
        int(t.get("cache_read") or 0),
        int(t.get("reasoning") or 0),
        _pct(t.get("cache_hit_rate")),
        (round(float(cost), 4) if cost is not None else ""),
        ("yes" if meta.get("cost_estimated") else ""),
        t.get("basis", "recorded"),
        meta.get("id") or "",
    ]


def _write_csv(rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_HEADER)
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


# ── public: build the archives ───────────────────────────────────────────────
# `items` is a list of {"meta": <session dict>, "messages": [<message dict>...]}.

def _filter_summary(filter_meta: dict | None, items: list[dict]) -> dict:
    total = 0
    for it in items:
        total += int((it["meta"].get("tokens") or {}).get("total") or 0)
    return {
        "exported_at": _now_iso(),
        "count": len(items),
        "total_tokens": total,
        "filter": filter_meta or {},
    }


def build_raw_zip(items: list[dict], filter_meta: dict | None = None) -> bytes:
    summary = _filter_summary(filter_meta, items)
    used: set[str] = set()
    rows = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        index_sessions = []
        for it in items:
            meta = it["meta"]
            msgs = it["messages"]
            name = _safe_name(meta.get("title") or meta.get("id"), used)
            slug = f"{meta.get('source')}__{re.sub(r'[^A-Za-z0-9._-]+', '-', str(meta.get('id')))[:60]}"
            z.writestr(f"sessions/{slug}.json",
                       json.dumps({"meta": meta, "messages": msgs}, ensure_ascii=False, indent=2))
            z.writestr(f"sessions/{slug}.md", render_markdown(meta, msgs))
            rows.append(_csv_row(name, meta))
            index_sessions.append({**meta, "file": f"sessions/{slug}"})
        z.writestr("index.json", json.dumps({**summary, "sessions": index_sessions},
                                            ensure_ascii=False, indent=2))
        z.writestr("index.csv", _write_csv(rows))
        z.writestr("README.txt",
                   "Session export\n==============\n\n"
                   f"Exported {summary['count']} session(s), "
                   f"{human_tokens(summary['total_tokens'])} total tokens, at {summary['exported_at']}.\n\n"
                   "- index.json / index.csv : metadata for every session (with the filter used).\n"
                   "- sessions/<id>.json      : full metadata + transcript (machine-readable).\n"
                   "- sessions/<id>.md        : the same transcript, human-readable.\n")
    return buf.getvalue()


def build_notion_zip(items: list[dict], filter_meta: dict | None = None) -> bytes:
    """Notion import layout: Sessions.csv + Sessions/<Name>.md (names match the CSV)."""
    summary = _filter_summary(filter_meta, items)
    used: set[str] = set()
    rows = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for it in items:
            meta = it["meta"]
            name = _safe_name(meta.get("title") or meta.get("id"), used)
            rows.append(_csv_row(name, meta))
            # filename MUST equal the Name cell so Notion attaches this as the page body
            z.writestr(f"Sessions/{name}.md", render_markdown(meta, it["messages"]))
        z.writestr("Sessions.csv", _write_csv(rows))
        z.writestr("HOW_TO_IMPORT.txt",
                   "Import into Notion\n==================\n\n"
                   "1. In Notion: Settings has nothing to do here — open the workspace sidebar and\n"
                   "   click  Import  →  CSV  (or  Markdown & CSV).\n"
                   "2. Select  Sessions.csv  from this zip (keep the  Sessions/  folder next to it —\n"
                   "   unzip first so both stay together).\n"
                   "3. Notion creates a database; each row's transcript (Sessions/<Name>.md) becomes\n"
                   "   that page's body. The columns become database properties:\n"
                   "     Source, Project, Created/Updated (dates), Model, Messages, token counts,\n"
                   "     Cache Hit Rate, Token Basis.\n"
                   "4. Re-create your filters inside Notion using those properties (e.g. filter by\n"
                   "   Source or Project, sort by Updated or Total Tokens).\n\n"
                   f"Exported {summary['count']} session(s) at {summary['exported_at']}.\n")
    return buf.getvalue()
