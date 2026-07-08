"""Cursor chat session parser.

Reads Cursor's global SQLite state DB (state.vscdb) READ-ONLY and defensively,
so it never locks or writes the live database (Cursor may be running).

Data layout:
  * ItemTable key 'composer.composerHeaders' -> master list of composers.
  * cursorDiskKV key 'composerData:{composerId}' -> per-composer detail.
  * cursorDiskKV key 'bubbleId:{composerId}:{bubbleId}' -> per-message bubble.

Only indexed primary-key lookups are performed against cursorDiskKV
(WHERE key=?), never a full table scan.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

SOURCE = "cursor"

DB = os.path.expanduser(
    "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb"
)

TITLE_MAX = 120


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def to_iso(value):
    """Convert epoch-seconds, epoch-millis, or an ISO string to
    'YYYY-MM-DDTHH:MM:SSZ'. Returns None if it cannot be parsed."""
    if value is None:
        return None
    # numeric epoch (int/float) or a numeric string
    if isinstance(value, (int, float)):
        num = float(value)
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # try numeric-looking strings first
        try:
            num = float(s)
        except ValueError:
            num = None
        if num is None:
            # assume it is already an ISO-8601 string
            try:
                iso = s.replace("Z", "+00:00")
                dt = datetime.fromisoformat(iso)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                return None
    else:
        return None

    # num is a number: decide seconds vs milliseconds.
    # Values >= 1e12 are almost certainly epoch-millis.
    if num >= 1e12:
        num = num / 1000.0
    try:
        dt = datetime.fromtimestamp(num, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_cache_hit_rate(input_t, cache_creation, cache_read):
    """cache_read / (input + cache_creation + cache_read), guarded."""
    denom = input_t + cache_creation + cache_read
    if not denom:
        return None
    return cache_read / denom


def _connect():
    """Open the live DB read-only and defensively. Try ?mode=ro first,
    then fall back to ?immutable=1 if the DB is locked."""
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=3.0)
        con.execute("PRAGMA busy_timeout=3000")
        # touch the DB to surface a lock error early
        con.execute("SELECT 1")
        return con
    except sqlite3.Error:
        # locked or otherwise unhappy: immutable ignores WAL/locks
        con = sqlite3.connect(f"file:{DB}?immutable=1", uri=True, timeout=3.0)
        con.execute("PRAGMA busy_timeout=3000")
        return con


def _get_value(con, table, key):
    """Indexed primary-key lookup. Returns parsed JSON or None."""
    try:
        cur = con.execute(f"SELECT value FROM {table} WHERE key=?", (key,))
        row = cur.fetchone()
    except sqlite3.Error:
        return None
    if not row or row[0] is None:
        return None
    raw = row[0]
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8", "replace")
        except Exception:
            return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def _trim(text):
    if not text:
        return ""
    text = " ".join(str(text).split())
    if len(text) > TITLE_MAX:
        return text[:TITLE_MAX].rstrip()
    return text


def _dig_model(model_config):
    """Best-effort dig for a string model id inside modelConfig."""
    if not isinstance(model_config, dict):
        return None
    for k in ("modelName", "model", "name", "id"):
        v = model_config.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # nested search
    for v in model_config.values():
        if isinstance(v, dict):
            found = _dig_model(v)
            if found:
                return found
    return None


def _empty_tokens(basis="context-snapshot"):
    return {
        "input": 0,
        "output": 0,
        "cache_creation": 0,
        "cache_read": 0,
        "reasoning": 0,
        "total": 0,
        "cache_hit_rate": None,
        "basis": basis,
    }


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def list_sessions():
    """One metadata dict per composer session, with aggregated tokens.
    Never raises for a single bad session — skips it and keeps going."""
    sessions = []
    con = None
    try:
        con = _connect()
    except sqlite3.Error:
        return sessions

    try:
        headers = _get_value(con, "ItemTable", "composer.composerHeaders")
        composers = []
        if isinstance(headers, dict):
            composers = headers.get("allComposers") or []

        for h in composers:
            try:
                if not isinstance(h, dict):
                    continue
                composer_id = h.get("composerId")
                if not composer_id:
                    continue

                detail = _get_value(con, "cursorDiskKV", f"composerData:{composer_id}")
                detail = detail if isinstance(detail, dict) else {}

                # project path
                project_path = None
                wsi = detail.get("workspaceIdentifier")
                if isinstance(wsi, dict):
                    uri = wsi.get("uri")
                    if isinstance(uri, dict):
                        fs = uri.get("fsPath")
                        if isinstance(fs, str) and fs.strip():
                            project_path = fs
                project = os.path.basename(project_path) if project_path else None

                # conversation headers (ordered turns)
                conv = detail.get("fullConversationHeadersOnly")
                conv = conv if isinstance(conv, list) else []
                message_count = len(conv)

                # title: header/composer name, else first user bubble text
                title = (
                    h.get("name")
                    or detail.get("name")
                    or ""
                )
                title = title.strip() if isinstance(title, str) else ""
                if not title:
                    # find first user bubble (type 1) and read its text
                    for turn in conv:
                        if not isinstance(turn, dict):
                            continue
                        if turn.get("type") == 1:
                            bid = turn.get("bubbleId")
                            if not bid:
                                continue
                            bubble = _get_value(
                                con,
                                "cursorDiskKV",
                                f"bubbleId:{composer_id}:{bid}",
                            )
                            if isinstance(bubble, dict):
                                bt = bubble.get("text")
                                if isinstance(bt, str) and bt.strip():
                                    title = bt.strip()
                                    break
                title = _trim(title) or "(untitled)"

                # timestamps
                created_at = to_iso(detail.get("createdAt") or h.get("createdAt"))
                updated_at = to_iso(h.get("lastUpdatedAt"))

                # model
                model = _dig_model(detail.get("modelConfig"))

                # tokens
                tokens = _empty_tokens("context-snapshot")
                breakdown = detail.get("promptTokenBreakdown")
                if isinstance(breakdown, dict):
                    total_used = breakdown.get("totalUsedTokens")
                    if isinstance(total_used, (int, float)) and total_used:
                        total_used = int(total_used)
                        tokens["input"] = total_used
                        tokens["total"] = total_used
                        # Cursor never records cache hits: always None.
                        tokens["cache_hit_rate"] = None

                sessions.append(
                    {
                        "id": composer_id,
                        "source": SOURCE,
                        "title": title,
                        "project_path": project_path,
                        "project": project,
                        "created_at": created_at,
                        "updated_at": updated_at,
                        "message_count": message_count,
                        "model": model,
                        "tokens": tokens,
                        "ref": composer_id,
                    }
                )
            except Exception:
                # never let one bad composer kill the whole listing
                continue
    finally:
        if con is not None:
            try:
                con.close()
            except sqlite3.Error:
                pass

    return sessions


def load_messages(session_id, ref):
    """Full ordered transcript for one composer. ref is the composerId."""
    composer_id = ref or session_id
    messages = []
    con = None
    try:
        con = _connect()
    except sqlite3.Error:
        return messages

    try:
        detail = _get_value(con, "cursorDiskKV", f"composerData:{composer_id}")
        if not isinstance(detail, dict):
            return messages
        conv = detail.get("fullConversationHeadersOnly")
        conv = conv if isinstance(conv, list) else []

        for turn in conv:
            try:
                if not isinstance(turn, dict):
                    continue
                bid = turn.get("bubbleId")
                if not bid:
                    continue
                bubble = _get_value(
                    con, "cursorDiskKV", f"bubbleId:{composer_id}:{bid}"
                )
                if not isinstance(bubble, dict):
                    continue

                text = bubble.get("text")
                text = text if isinstance(text, str) else ""

                # skip empty bubbles with no useful content
                if not text.strip():
                    continue

                btype = bubble.get("type")
                if btype is None:
                    btype = turn.get("type")
                role = "user" if btype == 1 else "assistant"

                ts = to_iso(bubble.get("createdAt"))

                messages.append(
                    {
                        "role": role,
                        "text": text,
                        "ts": ts,
                        "meta": {},
                    }
                )
            except Exception:
                continue
    finally:
        if con is not None:
            try:
                con.close()
            except sqlite3.Error:
                pass

    return messages
