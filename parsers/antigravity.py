"""Antigravity (IDE + CLI) session parser.

Reads per-conversation SQLite databases under
``~/.gemini/antigravity/conversations/*.db`` and
``~/.gemini/antigravity-cli/conversations/*.db``.

Each DB stores a trajectory: ``steps`` (protobuf payloads) and
``gen_metadata`` (per-generation model + token usage). Legacy encrypted
``.pb`` files are ignored — only the SQLite format is supported.

Standard library only. No imports from sibling parser modules.
"""

from __future__ import annotations

import glob
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone

SOURCE = "antigravity"

_TITLE_MAX = 120

# Conversational / tool step_type values observed in local DBs and
# confirmed by community parsers (splitrail, tokscale, agentsview).
_STEP_USER = 14
_STEP_THINKING = 15  # assistant reasoning / narrative
_STEP_TITLE = 23     # short agent-authored task title (not user)

# Tool-ish steps — summarized into role=tool lines.
_STEP_TOOL_TYPES = {
    5,   # write_to_file
    7,   # grep_search
    8,   # view_file
    9,   # list_dir
    17,  # view_file (variant / error)
    21,  # run_command
    38,  # call_mcp_tool
    132, # manage_task
}

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)
_OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{8,128}$")
_TOOL_NAME_RE = re.compile(
    r"^(?:run_command|view_file|write_to_file|list_dir|grep_search|"
    r"call_mcp_tool|manage_task|replace_file_content|"
    r"multi_replace_file_content|browser_subagent|read_url)$"
)


# ---------------------------------------------------------------------------
# protobuf wire-format (dependency-free)
# ---------------------------------------------------------------------------

def _read_varint(data: bytes, pos: int):
    result = 0
    shift = 0
    n = len(data)
    while True:
        if pos >= n:
            raise ValueError("eof")
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
        if shift > 70:
            raise ValueError("overflow")


def _proto_parse(data: bytes, depth: int = 0, max_depth: int = 8):
    """Parse protobuf wire format into a list of field dicts.

    Each field: {n, w, v?, s?, nested?}. Nested messages are decoded
    heuristically when the bytes look like a valid sub-message.
    """
    fields = []
    pos = 0
    n = len(data)
    while pos < n:
        try:
            key, pos = _read_varint(data, pos)
        except ValueError:
            break
        field_num = key >> 3
        wire = key & 7
        if field_num == 0:
            break
        try:
            if wire == 0:  # varint
                val, pos = _read_varint(data, pos)
                fields.append({"n": field_num, "w": "v", "v": val})
            elif wire == 1:  # 64-bit
                if pos + 8 > n:
                    break
                pos += 8
                fields.append({"n": field_num, "w": "64"})
            elif wire == 5:  # 32-bit
                if pos + 4 > n:
                    break
                pos += 4
                fields.append({"n": field_num, "w": "32"})
            elif wire == 2:  # length-delimited
                length, pos = _read_varint(data, pos)
                if pos + length > n:
                    break
                chunk = data[pos : pos + length]
                pos += length
                entry = {"n": field_num, "w": "b", "len": length}
                try:
                    text = chunk.decode("utf-8")
                    if text and all(c in "\n\r\t" or ord(c) >= 32 for c in text):
                        entry["s"] = text
                except UnicodeDecodeError:
                    pass
                # Don't reinterpret human prose as a nested protobuf message —
                # UTF-8 chat text often happens to decode as plausible fields,
                # which would hide the real string from collectors.
                looks_like_prose = (
                    "s" in entry
                    and len(entry["s"]) >= 24
                    and any(c.isspace() for c in entry["s"])
                )
                if depth < max_depth and not looks_like_prose:
                    nested = _proto_parse(chunk, depth + 1, max_depth)
                    if nested and all(1 <= f["n"] <= 100_000 for f in nested):
                        entry["nested"] = nested
                fields.append(entry)
            else:
                break
        except ValueError:
            break
    return fields


def _fields_named(fields, num):
    return [f for f in fields if f["n"] == num]


def _first_string(fields, num):
    for f in _fields_named(fields, num):
        if "s" in f:
            return f["s"]
    return None


def _first_varint(fields, num):
    for f in _fields_named(fields, num):
        if f["w"] == "v":
            return int(f["v"])
    return None


def _first_nested(fields, num):
    for f in _fields_named(fields, num):
        if "nested" in f:
            return f["nested"]
    return None


def _collect_strings(fields, out=None):
    if out is None:
        out = []
    for f in fields:
        if "s" in f and "nested" not in f:
            out.append(f["s"])
        if "nested" in f:
            _collect_strings(f["nested"], out)
    return out


def _earliest_timestamp(fields):
    """Return earliest plausible google.protobuf.Timestamp as ISO-Z, or None."""
    best = None

    def walk(fs):
        nonlocal best
        # A timestamp message is {1: seconds, 2?: nanos} — both varints only.
        if fs and all(f["w"] == "v" and f["n"] in (1, 2) for f in fs):
            sec = _first_varint(fs, 1)
            if sec is not None and 946_684_800 < sec < 4_102_444_800:
                nanos = _first_varint(fs, 2) or 0
                iso = _epoch_to_iso(sec, nanos)
                if iso and (best is None or iso < best):
                    best = iso
        for f in fs:
            if "nested" in f:
                walk(f["nested"])

    walk(fields)
    return best


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def to_iso(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return _epoch_to_iso(float(value))
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return _epoch_to_iso(float(s))
        except ValueError:
            pass
        try:
            iso = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None
    return None


def _epoch_to_iso(sec, nanos: int = 0):
    try:
        if sec > 1e12:  # millis
            sec = sec / 1000.0
        dt = datetime.fromtimestamp(float(sec), tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


def _compute_cache_hit_rate(input_t, cache_creation, cache_read, has_cache_read):
    if not has_cache_read:
        return None
    denom = input_t + cache_creation + cache_read
    if denom <= 0:
        return None
    return cache_read / denom


def _file_uri_to_path(uri: str | None):
    if not uri:
        return None
    s = uri.strip()
    if s.startswith("file://"):
        s = s[7:]
        # file:///Users/... → /Users/...
        if s.startswith("//"):
            s = s[1:]
        elif len(s) >= 3 and s[0] == "/" and s[1].isalpha() and s[2] == ":":
            # file:///C:/... on Windows-ish
            s = s[1:]
    return s or None


def _conversation_dirs():
    home = os.path.expanduser("~")
    dirs = [
        os.path.join(home, ".gemini", "antigravity", "conversations"),
        os.path.join(home, ".gemini", "antigravity-cli", "conversations"),
    ]
    # Optional override used by some Gemini CLI installs.
    cli_home = os.environ.get("GEMINI_CLI_HOME") or os.environ.get("ANTIGRAVITY_HOME")
    if cli_home:
        dirs.append(os.path.join(os.path.expanduser(cli_home), "conversations"))
    # Dedup while preserving order.
    seen = set()
    out = []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _connect(path: str):
    """Open a conversation DB read-only. Prefer immutable — some Antigravity
    DBs refuse ``mode=ro`` when WAL sidecars are present / locked."""
    abs_path = os.path.abspath(path)
    for uri in (
        f"file:{abs_path}?immutable=1",
        f"file:{abs_path}?mode=ro",
        f"file:{abs_path}?mode=ro&immutable=1",
    ):
        try:
            con = sqlite3.connect(uri, uri=True, timeout=3.0)
            con.execute("PRAGMA busy_timeout=3000")
            con.execute("SELECT 1")
            return con
        except sqlite3.Error:
            try:
                con.close()
            except Exception:
                pass
    raise sqlite3.Error(f"unable to open {path}")


def _is_noisy(s: str) -> bool:
    t = s.strip()
    if not t or len(t) < 4:
        return True
    if _UUID_RE.match(t):
        return True
    if _TOOL_NAME_RE.match(t):
        return True
    if t.startswith("MODEL_PLACEHOLDER_"):
        return True
    if t.startswith("{") and (
        '"toolAction"' in t or '"toolSummary"' in t or '"DirectoryPath"' in t
        or '"AbsolutePath"' in t or '"CommandLine"' in t
    ):
        return True
    if t.startswith("file://"):
        return True
    if "/.gemini/" in t and (t.startswith("/Users/") or t.startswith("/home/") or t.startswith("C:\\")):
        return True
    if t.startswith(("command(", "read_url(", "mcp(", "execute_url(", "write_file(")):
        return True
    if t in ("sessionID", "trajectory_id", "last_step_index", "auto", "true", "false"):
        return True
    # Protobuf field-name lists like "AbsolutePath*\ntoolAction*"
    if "*" in t and any(k in t for k in ("toolAction", "toolSummary", "AbsolutePath")):
        return True
    if _OPAQUE_ID_RE.match(t) and not any(c in t for c in " \n\t/"):
        if any(c.isalpha() for c in t):
            return True
    return False


def _clean_strings(strs, step_type: int):
    cleaned = []
    seen = set()
    for s in strs:
        t = s.strip()
        if _is_noisy(t) or t in seen:
            continue
        seen.add(t)
        cleaned.append(t)
    if step_type == _STEP_USER:
        prompt = _best_user_prompt(cleaned)
        return [prompt] if prompt else []
    if step_type == _STEP_THINKING:
        # Thinking text is often split across multiple protobuf string fields.
        narratives = [
            s for s in cleaned
            if len(s) >= 20 or (any(c.isspace() for c in s) and len(s) >= 8)
        ]
        if narratives:
            return ["".join(narratives)]
        return cleaned[:1]
    if step_type in _STEP_TOOL_TYPES:
        return _pick_tool_summary(cleaned)
    return cleaned


def _pick_tool_summary(strs):
    """Prefer short human summaries over giant file dumps / schema JSON."""
    if not strs:
        return []
    scored = []
    for s in strs:
        score = 0
        if 8 <= len(s) <= 160:
            score += 50
        if any(c.isspace() for c in s):
            score += 20
        if s.startswith("{") or s.startswith("<") or s.startswith("#"):
            score -= 40
        if len(s) > 800:
            score -= 60
        scored.append((score, s))
    scored.sort(key=lambda x: (-x[0], len(x[1])))
    best = scored[0][1]
    detail = None
    for _, s in scored[1:]:
        if s != best and 8 <= len(s) <= 300 and not s.startswith("{"):
            detail = s
            break
    return [best, detail] if detail else [best]


def _best_user_prompt(strs):
    best = None
    best_score = -1
    for s in strs:
        score = _prompt_score(s)
        if score > best_score:
            best = s
            best_score = score
    return best if best_score > 0 else None


def _prompt_score(s: str) -> int:
    t = s.strip()
    if not t or _is_noisy(t):
        return -1
    score = len(t)
    if any(c.isspace() for c in t):
        score += 50
    if t.startswith("{") or t.startswith("["):
        score -= 100
    if t.startswith("/") or t.startswith("file://"):
        score -= 100
    if not any(c.isalpha() for c in t):
        score -= 100
    return score


def _trim_title(text: str) -> str:
    s = " ".join(text.split())
    if len(s) > _TITLE_MAX:
        s = s[:_TITLE_MAX].rstrip()
    return s


# ---------------------------------------------------------------------------
# gen_metadata / trajectory_metadata decoding
# ---------------------------------------------------------------------------

def _parse_gen_usage(data: bytes):
    """Return {model, response_id, input, output, cache_read, reasoning, ts}.

    Field map (GeneratorMetadata / GenAI usage), matching tokscale:
      envelope #1
        #19 model id, #21 display name
        #4 usage: #1 system + #2 new input, #5 cache_read, #3 reasoning,
                  #9 output text, #11 response id
        #9.4 timestamp
    """
    fields = _proto_parse(data)
    env = _first_nested(fields, 1)
    if not env:
        return None

    model = _first_string(env, 19) or _first_string(env, 21)
    usage = _first_nested(env, 4) or []
    f1 = _first_varint(usage, 1) or 0
    f2 = _first_varint(usage, 2) or 0
    f3 = _first_varint(usage, 3) or 0
    f5 = _first_varint(usage, 5) or 0
    f9 = _first_varint(usage, 9) or 0
    rid = _first_string(usage, 11)

    # Prefer the generation timestamp under envelope.#9.#4 when present.
    ts = None
    meta9 = _first_nested(env, 9)
    if meta9:
        ts_fields = _first_nested(meta9, 4)
        if ts_fields:
            sec = _first_varint(ts_fields, 1)
            if sec is not None:
                ts = _epoch_to_iso(sec, _first_varint(ts_fields, 2) or 0)
    if ts is None:
        ts = _earliest_timestamp(fields)

    return {
        "model": model,
        "response_id": rid,
        "input": f1 + f2,  # uncached (system + newly processed)
        "output": f9,
        "cache_read": f5,
        "reasoning": f3,
        "ts": ts,
    }


def _parse_trajectory_meta(data: bytes):
    """Extract workspace path + created_at from trajectory_metadata_blob."""
    fields = _proto_parse(data)
    project_path = None
    # #1.#1 / #1.#2 / #7 are file:// workspace URIs
    outer = _first_nested(fields, 1)
    if outer:
        for num in (1, 2):
            uri = _first_string(outer, num)
            project_path = _file_uri_to_path(uri)
            if project_path:
                break
    if not project_path:
        project_path = _file_uri_to_path(_first_string(fields, 7))

    created_at = None
    ts_fields = _first_nested(fields, 2)
    if ts_fields:
        sec = _first_varint(ts_fields, 1)
        if sec is not None:
            created_at = _epoch_to_iso(sec, _first_varint(ts_fields, 2) or 0)
    if created_at is None:
        created_at = _earliest_timestamp(fields)

    return project_path, created_at


def _cli_history_titles():
    """Optional title hints from antigravity-cli/history.jsonl."""
    path = os.path.expanduser("~/.gemini/antigravity-cli/history.jsonl")
    out = {}
    if not os.path.isfile(path):
        return out
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    import json

                    obj = json.loads(line)
                except (ValueError, TypeError):
                    continue
                cid = obj.get("conversationId")
                display = obj.get("display")
                if cid and isinstance(display, str) and display.strip():
                    out[str(cid)] = display.strip()
    except OSError:
        pass
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_sessions():
    history_titles = _cli_history_titles()
    sessions = []
    for directory in _conversation_dirs():
        pattern = os.path.join(directory, "*.db")
        for path in sorted(glob.glob(pattern)):
            # Skip WAL/SHM sidecars (glob *.db already excludes them).
            try:
                meta = _summarize_db(path, history_titles)
                if meta is not None:
                    sessions.append(meta)
            except Exception:
                continue
    return sessions


def _summarize_db(path: str, history_titles: dict):
    basename = os.path.basename(path)
    session_id = basename[:-3] if basename.endswith(".db") else basename

    try:
        con = _connect(path)
    except sqlite3.Error:
        return None

    try:
        # Prefer cascade_id from trajectory_meta when present.
        try:
            row = con.execute(
                "SELECT cascade_id, trajectory_id FROM trajectory_meta LIMIT 1"
            ).fetchone()
            if row and row[0]:
                session_id = row[0]
        except sqlite3.Error:
            pass

        project_path = None
        created_at = None
        try:
            blob = con.execute(
                "SELECT data FROM trajectory_metadata_blob WHERE id='main'"
            ).fetchone()
            if blob and blob[0]:
                project_path, created_at = _parse_trajectory_meta(blob[0])
        except sqlite3.Error:
            pass

        input_t = output_t = cache_read = reasoning = 0
        has_cache_read = False
        models = Counter()
        seen_responses = set()
        updated_at = created_at

        try:
            for idx, data in con.execute("SELECT idx, data FROM gen_metadata"):
                if not data:
                    continue
                info = _parse_gen_usage(data)
                if not info:
                    continue
                key = info.get("response_id") or f"idx:{idx}"
                if key in seen_responses:
                    continue
                seen_responses.add(key)
                input_t += info["input"]
                output_t += info["output"]
                reasoning += info["reasoning"]
                if info["cache_read"]:
                    cache_read += info["cache_read"]
                    has_cache_read = True
                if info.get("model"):
                    models[info["model"]] += 1
                if info.get("ts"):
                    if updated_at is None or info["ts"] > updated_at:
                        updated_at = info["ts"]
                    if created_at is None or info["ts"] < created_at:
                        created_at = info["ts"]
        except sqlite3.Error:
            pass

        title = ""
        message_count = 0
        try:
            for idx, step_type, payload in con.execute(
                "SELECT idx, step_type, step_payload FROM steps ORDER BY idx"
            ):
                if not payload:
                    continue
                if step_type == _STEP_USER:
                    message_count += 1
                    if not title:
                        fields = _proto_parse(payload)
                        cleaned = _clean_strings(_collect_strings(fields), step_type)
                        if cleaned:
                            title = _trim_title(cleaned[0])
                elif step_type == _STEP_THINKING:
                    message_count += 1
                elif step_type in _STEP_TOOL_TYPES:
                    message_count += 1
                elif step_type == _STEP_TITLE and not title:
                    fields = _proto_parse(payload)
                    cleaned = _clean_strings(_collect_strings(fields), step_type)
                    if cleaned:
                        title = _trim_title(cleaned[0].split("\n", 1)[0])
        except sqlite3.Error:
            pass

        if not title:
            title = _trim_title(history_titles.get(session_id) or "") or session_id

        if created_at is None or updated_at is None:
            try:
                mtime_iso = to_iso(os.path.getmtime(path))
            except OSError:
                mtime_iso = None
            if created_at is None:
                created_at = mtime_iso
            if updated_at is None:
                updated_at = mtime_iso

        project = os.path.basename(project_path) if project_path else None
        total = input_t + output_t + cache_read + reasoning
        tokens = {
            "input": input_t,
            "output": output_t,
            "cache_creation": 0,
            "cache_read": cache_read,
            "reasoning": reasoning,
            "total": total,
            "cache_hit_rate": _compute_cache_hit_rate(
                input_t, 0, cache_read, has_cache_read
            ),
            "basis": "recorded",
        }
        model = models.most_common(1)[0][0] if models else None

        return {
            "id": session_id,
            "source": SOURCE,
            "title": title,
            "project_path": project_path,
            "project": project,
            "created_at": created_at,
            "updated_at": updated_at,
            "message_count": message_count,
            "model": model,
            "tokens": tokens,
            "ref": os.path.abspath(path),
        }
    finally:
        con.close()


def load_messages(session_id, ref):
    messages = []
    if not ref or not os.path.exists(ref):
        return messages
    try:
        con = _connect(ref)
    except sqlite3.Error:
        return messages

    try:
        # Map step idx → model from gen_metadata when available.
        gen_model = {}
        try:
            for idx, data in con.execute("SELECT idx, data FROM gen_metadata"):
                if not data:
                    continue
                info = _parse_gen_usage(data)
                if info and info.get("model"):
                    gen_model[idx] = info["model"]
        except sqlite3.Error:
            pass

        try:
            rows = con.execute(
                "SELECT idx, step_type, step_payload FROM steps ORDER BY idx"
            )
        except sqlite3.Error:
            return messages

        for idx, step_type, payload in rows:
            if not payload:
                continue
            fields = _proto_parse(payload)
            cleaned = _clean_strings(_collect_strings(fields), step_type)
            ts = _earliest_timestamp(fields)

            if step_type == _STEP_USER:
                if not cleaned:
                    continue
                messages.append(
                    {
                        "role": "user",
                        "text": cleaned[0],
                        "ts": ts,
                        "meta": {},
                    }
                )
            elif step_type == _STEP_THINKING:
                if not cleaned:
                    continue
                text = "\n\n".join(cleaned)
                meta = {"thinking": True}
                if idx in gen_model:
                    meta["model"] = gen_model[idx]
                messages.append(
                    {
                        "role": "assistant",
                        "text": text,
                        "ts": ts,
                        "meta": meta,
                    }
                )
            elif step_type in _STEP_TOOL_TYPES:
                if not cleaned:
                    continue
                summary = cleaned[0]
                detail = cleaned[1] if len(cleaned) > 1 else ""
                text = f"[tool] {summary}"
                if detail and detail != summary:
                    text += "\n" + detail[:500]
                messages.append(
                    {
                        "role": "tool",
                        "text": text,
                        "ts": ts,
                        "meta": {"step_type": step_type},
                    }
                )
            # Other step types (permissions, notifications, internal) skipped.
    finally:
        con.close()

    return messages
