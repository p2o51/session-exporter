"""Model pricing → per-session cost (cache-aware).

Rates live in the editable pricing.json next to this file. Cost is computed
source-aware because the three tools record token usage with different semantics:

  * Claude   — usage.input_tokens is UNCACHED input; cache writes (5m/1h) and
               cache reads are separate line items. Anthropic bills cache writes
               at 1.25x (5-min) / 2x (1-hour) of input and cache reads at 0.1x.
  * Codex    — total_token_usage.input_tokens INCLUDES the cached portion, so
               uncached = input - cached; output already includes reasoning.
  * Cursor   — only a context-window snapshot is recorded, not actual spend, so
               cost is reported as unknown (None).

Unknown models (no rate in pricing.json) are reported as unknown rather than
guessed, so a "—" in the UI always means "not priced", never "free".
"""

from __future__ import annotations

import json
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PRICING_FILE = os.path.join(APP_DIR, "pricing.json")

_M = 1_000_000
_cache: dict = {"mtime": None, "data": None}


def _load() -> dict:
    try:
        mt = os.path.getmtime(PRICING_FILE)
    except OSError:
        return {"models": {}, "aliases": {}}
    if _cache["data"] is None or _cache["mtime"] != mt:
        try:
            with open(PRICING_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return {"models": {}, "aliases": {}}
        models = {str(k).lower(): v for k, v in (raw.get("models") or {}).items()}
        aliases = {str(k).lower(): str(v).lower() for k, v in (raw.get("aliases") or {}).items()}
        _cache.update(mtime=mt, data={"models": models, "aliases": aliases})
    return _cache["data"]


def reload() -> None:
    """Force a re-read of pricing.json on the next lookup."""
    _cache["data"] = None
    _cache["mtime"] = None


def rates_for(model: str | None) -> dict | None:
    if not model:
        return None
    data = _load()
    key = str(model).strip().lower()
    key = data["aliases"].get(key, key)
    return data["models"].get(key)


def cost_for(session: dict) -> dict:
    """Return {usd, known, estimated} for one session dict."""
    t = session.get("tokens") or {}
    if t.get("basis") != "recorded":
        return {"usd": None, "known": False, "estimated": False}
    r = rates_for(session.get("model"))
    if not r:
        return {"usd": None, "known": False, "estimated": False}

    inp = int(t.get("input") or 0)
    out = int(t.get("output") or 0)
    cr = int(t.get("cache_read") or 0)
    in_rate = float(r.get("input") or 0)
    out_rate = float(r.get("output") or 0)
    cr_rate = float(r["cache_read"]) if "cache_read" in r else in_rate * 0.1

    usd = out / _M * out_rate

    if session.get("source") == "claude":
        usd += inp / _M * in_rate
        usd += cr / _M * cr_rate
        cw5_rate = float(r.get("cache_write_5m", in_rate * 1.25))
        cw1_rate = float(r.get("cache_write_1h", in_rate * 2))
        c5 = t.get("cache_creation_5m")
        c1 = t.get("cache_creation_1h")
        if c5 is None and c1 is None:
            usd += int(t.get("cache_creation") or 0) / _M * cw5_rate
        else:
            usd += int(c5 or 0) / _M * cw5_rate
            usd += int(c1 or 0) / _M * cw1_rate
    else:  # codex / openai: input_tokens already includes the cached portion
        uncached = max(0, inp - cr)
        usd += uncached / _M * in_rate
        usd += cr / _M * cr_rate

    return {"usd": round(usd, 4), "known": True, "estimated": bool(r.get("estimated"))}


def annotate(sessions: list[dict]) -> list[dict]:
    """Attach cost_usd / cost_known / cost_estimated to each session in place."""
    for s in sessions:
        c = cost_for(s)
        s["cost_usd"] = c["usd"]
        s["cost_known"] = c["known"]
        s["cost_estimated"] = c["estimated"]
    return sessions


def aggregate_cost(sessions: list[dict]) -> dict:
    """Sum known cost across sessions; report how many were priced vs not."""
    total = 0.0
    priced = unpriced = 0
    estimated = False
    for s in sessions:
        if s.get("cost_known") and s.get("cost_usd") is not None:
            total += float(s["cost_usd"])
            priced += 1
            estimated = estimated or bool(s.get("cost_estimated"))
        else:
            unpriced += 1
    return {"usd": round(total, 4), "priced": priced, "unpriced": unpriced, "estimated": estimated}


def table() -> dict:
    """Expose the resolved model→rates map (for a pricing view)."""
    return _load()["models"]
