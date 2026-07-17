"""Session parser registry.

Each source parser (claude, codex, cursor, antigravity, pi, kimi) is a module exposing
two functions that together form the PARSER CONTRACT. The rest of the app only
ever talks to parsers through this contract, so the sources stay fully decoupled.

────────────────────────────────────────────────────────────────────────────
PARSER CONTRACT
────────────────────────────────────────────────────────────────────────────

SOURCE: str
    The source id, one of "claude" | "codex" | "cursor" | "antigravity" | "pi" | "kimi".

def list_sessions() -> list[dict]:
    Return one metadata dict per session. Does NOT include full messages, but
    DOES include aggregated token totals (cheap enough; cached upstream).
    Never raises for a single bad session — skip it and keep going.

    Session metadata dict shape:
    {
      "id":            str,          # unique within the source
      "source":        SOURCE,
      "title":         str,          # short human title (first user prompt / name)
      "project_path":  str | None,   # absolute project folder, or None
      "project":       str | None,   # display basename of project_path
      "created_at":    str | None,   # ISO-8601 (UTC, e.g. "2026-06-19T00:02:06Z")
      "updated_at":    str | None,   # ISO-8601
      "message_count": int,
      "model":         str | None,   # best-effort primary model id
      "tokens": {
          "input":          int,
          "output":         int,
          "cache_creation": int,     # tokens written to cache (Claude); 0 if N/A
          "cache_read":     int,     # tokens served from cache
          "reasoning":      int,     # reasoning/thinking tokens (Codex); 0 if N/A
          "total":          int,
          "cache_hit_rate": float | None,  # 0..1, or None when the source can't report it
          "basis":          str,     # "recorded" | "context-snapshot" | "estimated"
      },
      "ref":           str,          # opaque handle load_messages() understands
    }

def load_messages(session_id: str, ref: str) -> list[dict]:
    Return the full ordered transcript for one session.

    Message dict shape:
    {
      "role":  str,        # "user" | "assistant" | "system" | "tool" | "reasoning"
      "text":  str,        # plain-text rendering (tool calls summarized inline)
      "ts":    str | None, # ISO-8601 timestamp
      "meta":  dict,       # optional extras (e.g. {"sidechain": True, "model": ...})
    }

Rules every parser follows:
  * Standard library only. No third-party imports.
  * Absolute paths expanded from ~ ; tolerate missing files/dirs (return []).
  * `basis` is honest: "recorded" = provider-reported usage numbers,
    "context-snapshot" = last context-window size (Cursor), "estimated" = heuristic.
  * cache_hit_rate = cache_read / (input + cache_creation + cache_read) when the
    source records cache reads; else None.
"""

from __future__ import annotations

import importlib

# Order here is the display order in the UI.
_SOURCE_MODULES = ["claude", "codex", "cursor", "antigravity", "pi", "kimi"]

_loaded: dict = {}


def _get(source: str):
    if source not in _loaded:
        _loaded[source] = importlib.import_module(f"parsers.{source}")
    return _loaded[source]


def available_sources() -> list[str]:
    out = []
    for name in _SOURCE_MODULES:
        try:
            _get(name)
            out.append(name)
        except Exception as e:  # a parser that fails to import is simply skipped
            print(f"[parsers] source '{name}' unavailable: {e}")
    return out


def list_sessions(source: str) -> list[dict]:
    try:
        return _get(source).list_sessions()
    except Exception as e:
        print(f"[parsers] list_sessions({source}) failed: {e}")
        return []


def load_messages(source: str, session_id: str, ref: str) -> list[dict]:
    return _get(source).load_messages(session_id, ref)
