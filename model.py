"""In-memory + on-disk session index built on top of the parser contract.

The store scans every available source once, keeps the metadata in memory for the
life of the process, and persists it to a small on-disk cache keyed by a cheap
"fingerprint" of the underlying files so restarts are instant when nothing changed.
Full transcripts are always loaded lazily (never cached here).
"""

from __future__ import annotations

import glob
import json
import os
import threading
import time

import parsers
import pricing

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(APP_DIR, ".cache")
CACHE_FILE = os.path.join(CACHE_DIR, "index.json")


# ── cheap fingerprint of the raw data ───────────────────────────────────────
# Mirrors where each parser reads from, but only stats files (never parses them),
# so we can tell "nothing changed since last scan" without the expensive work.

def _fingerprint() -> str:
    parts: list[str] = []

    def stat_glob(pattern: str, recursive: bool = False):
        for p in glob.glob(os.path.expanduser(pattern), recursive=recursive):
            try:
                st = os.stat(p)
                parts.append(f"{p}:{int(st.st_mtime)}:{st.st_size}")
            except OSError:
                pass

    stat_glob("~/.claude/projects/*/*.jsonl")
    stat_glob("~/.codex/sessions/**/rollout-*.jsonl", recursive=True)
    stat_glob("~/.codex/archived_sessions/rollout-*.jsonl")
    # Cursor: the single global db mtime is a good enough signal.
    stat_glob("~/Library/Application Support/Cursor/User/globalStorage/state.vscdb")
    # Antigravity IDE + CLI: one SQLite DB per conversation.
    stat_glob("~/.gemini/antigravity/conversations/*.db")
    stat_glob("~/.gemini/antigravity-cli/conversations/*.db")
    # Pi Agent: JSONL transcripts under encoded cwd folders.
    stat_glob("~/.pi/agent/sessions/**/*.jsonl", recursive=True)
    # Kimi Code: session metadata plus one wire log per main/sub-Agent.
    kimi_root = os.path.expanduser(os.environ.get("KIMI_CODE_HOME", "~/.kimi-code"))
    stat_glob(os.path.join(kimi_root, "session_index.jsonl"))
    stat_glob(os.path.join(kimi_root, "sessions", "**", "state.json"), recursive=True)
    stat_glob(os.path.join(kimi_root, "sessions", "**", "wire.jsonl"), recursive=True)

    parts.sort()
    import hashlib

    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()


class Store:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: list[dict] | None = None
        self._by_key: dict[tuple[str, str], dict] = {}
        self._sources: list[str] = []
        self._generated_at: float = 0.0
        self._fp: str = ""

    # ── public API ──────────────────────────────────────────────────────────
    def index(self, refresh: bool = False) -> dict:
        with self._lock:
            if self._sessions is not None and not refresh:
                return self._payload()

            if not refresh:
                cached = self._load_disk_cache()
                if cached is not None:
                    self._install(cached["sessions"], cached["sources"], cached["fingerprint"])
                    return self._payload()

            self._scan()
            return self._payload()

    def get_session(self, source: str, sid: str) -> dict | None:
        if self._sessions is None:
            self.index()
        return self._by_key.get((source, sid))

    def load_messages(self, source: str, sid: str) -> list[dict]:
        meta = self.get_session(source, sid)
        if not meta:
            return []
        try:
            return parsers.load_messages(source, sid, meta.get("ref", ""))
        except Exception as e:  # noqa: BLE001
            return [{"role": "system", "text": f"[failed to load transcript: {e}]", "ts": None, "meta": {}}]

    # ── internals ───────────────────────────────────────────────────────────
    def _scan(self) -> None:
        sources = parsers.available_sources()
        all_sessions: list[dict] = []
        for src in sources:
            all_sessions.extend(parsers.list_sessions(src))
        fp = _fingerprint()
        self._install(all_sessions, sources, fp)
        self._write_disk_cache()

    def reprice(self) -> dict:
        """Re-read pricing.json and recompute cost on the in-memory index
        (cheap — no re-scan of the raw data)."""
        with self._lock:
            if self._sessions is not None:
                pricing.reload()
                pricing.annotate(self._sessions)
            return self._payload()

    def _install(self, sessions: list[dict], sources: list[str], fp: str) -> None:
        # cost is applied on every install (scan or cache load) so a pricing.json
        # edit takes effect on relaunch without re-parsing the raw data.
        pricing.annotate(sessions)
        # newest first by updated_at, falling back to created_at
        sessions.sort(key=lambda s: (s.get("updated_at") or s.get("created_at") or ""), reverse=True)
        self._sessions = sessions
        self._by_key = {(s["source"], s["id"]): s for s in sessions}
        self._sources = sources
        self._fp = fp
        self._generated_at = time.time()

    def _payload(self) -> dict:
        return {
            "sources": self._sources,
            "sessions": self._sessions or [],
            "generated_at": self._generated_at,
            "count": len(self._sessions or []),
        }

    def _load_disk_cache(self) -> dict | None:
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return None
        if data.get("fingerprint") != _fingerprint():
            return None
        return data

    def _write_disk_cache(self) -> None:
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            tmp = CACHE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    {"fingerprint": self._fp, "sources": self._sources, "sessions": self._sessions},
                    f,
                    ensure_ascii=False,
                )
            os.replace(tmp, CACHE_FILE)
        except OSError:
            pass


# ── token aggregation ───────────────────────────────────────────────────────

def empty_tokens() -> dict:
    return {
        "input": 0, "output": 0, "cache_creation": 0, "cache_read": 0,
        "reasoning": 0, "total": 0, "cache_hit_rate": None, "basis": "recorded",
    }


def aggregate_tokens(sessions: list[dict]) -> dict:
    agg = empty_tokens()
    bases: set[str] = set()
    cacheable = 0  # input+cache_creation+cache_read across sessions that record cache
    cache_read = 0
    any_cache = False
    for s in sessions:
        t = s.get("tokens") or {}
        for k in ("input", "output", "cache_creation", "cache_read", "reasoning", "total"):
            agg[k] += int(t.get(k) or 0)
        if t.get("basis"):
            bases.add(t["basis"])
        if t.get("cache_hit_rate") is not None:
            any_cache = True
            cache_read += int(t.get("cache_read") or 0)
            cacheable += int(t.get("input") or 0) + int(t.get("cache_creation") or 0) + int(t.get("cache_read") or 0)
    agg["cache_hit_rate"] = (cache_read / cacheable) if (any_cache and cacheable) else None
    agg["basis"] = "mixed" if len(bases) > 1 else (next(iter(bases)) if bases else "recorded")
    return agg


store = Store()
