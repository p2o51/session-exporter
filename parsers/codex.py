"""Codex (~/.codex) session parser.

Reads Codex rollout JSONL files and exposes the shared parser contract:
    SOURCE, list_sessions(), load_messages(session_id, ref)

Stdlib only.
"""

import glob
import json
import os
from datetime import datetime, timezone

SOURCE = "codex"

# input_text blocks whose text begins with one of these are synthetic system
# context injected by the harness, not a genuine human turn.
_SYSTEM_PREFIXES = (
    "<permissions instructions>",
    "<app-context>",
    "<environment_context>",
    "<user_instructions>",
)

_TITLE_MAX = 120


def _session_files():
    """All rollout files under sessions/ (recursive) and archived_sessions/."""
    paths = []
    paths.extend(
        glob.glob(
            os.path.expanduser("~/.codex/sessions/**/rollout-*.jsonl"),
            recursive=True,
        )
    )
    paths.extend(
        glob.glob(
            os.path.expanduser("~/.codex/archived_sessions/**/rollout-*.jsonl"),
            recursive=True,
        )
    )
    # de-dup while preserving order
    seen = set()
    out = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def to_iso(value):
    """Convert epoch-seconds, epoch-millis, or an ISO string to
    'YYYY-MM-DDTHH:MM:SSZ' (UTC). Returns None if unparseable."""
    if value is None:
        return None
    # numeric epoch
    if isinstance(value, (int, float)):
        secs = float(value)
        # treat very large values as milliseconds
        if secs > 1e11:
            secs /= 1000.0
        try:
            dt = datetime.fromtimestamp(secs, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # numeric string?
        try:
            return to_iso(float(s)) if s.replace(".", "", 1).isdigit() else _parse_iso(s)
        except ValueError:
            return _parse_iso(s)
    return None


def _parse_iso(s):
    txt = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        # last resort: keep first 19 chars if they look like a timestamp
        try:
            dt = datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cache_hit_rate(cache_read, input_tokens, cache_creation):
    denom = input_tokens + cache_creation + cache_read
    if cache_read and denom > 0:
        return cache_read / denom
    return None


def _block_text(content):
    """Concatenate text from message content blocks of the relevant types."""
    if not isinstance(content, list):
        return ""
    parts = []
    for b in content:
        if isinstance(b, dict) and b.get("type") in ("input_text", "output_text", "text"):
            t = b.get("text")
            if isinstance(t, str):
                parts.append(t)
    return "".join(parts)


def _is_system_text(text):
    stripped = text.lstrip()
    return any(stripped.startswith(pfx) for pfx in _SYSTEM_PREFIXES)


def _reasoning_text(payload):
    summary = payload.get("summary")
    parts = []
    if isinstance(summary, list):
        for entry in summary:
            if isinstance(entry, dict):
                t = entry.get("text")
                if isinstance(t, str) and t:
                    parts.append(t)
            elif isinstance(entry, str) and entry:
                parts.append(entry)
    text = "\n".join(parts).strip()
    return text if text else "[reasoning]"


def _empty_tokens():
    return {
        "input": 0,
        "output": 0,
        "cache_creation": 0,
        "cache_read": 0,
        "reasoning": 0,
        "total": 0,
        "cache_hit_rate": None,
        "basis": "recorded",
    }


# Codex rollout files can reach hundreds of MB. Everything we need lives in the
# head (session_meta, model, first human message) and tail (final token_count),
# so we stream the file to count messages at the byte level and only JSON-parse
# those two chunks — turning a 650 MB full-parse into a couple of KB of work.
_HEAD_BYTES = 1 << 20  # 1 MiB
_TAIL_BYTES = 1 << 19  # 512 KiB
_MSG_MARKER = b'"type":"message"'


def _objs_from_chunk(chunk, drop_first, drop_last):
    if not chunk:
        return []
    lines = chunk.split(b"\n")
    if drop_last and lines:
        lines = lines[:-1]
    if drop_first and lines:
        lines = lines[1:]
    out = []
    for lb in lines:
        lb = lb.strip()
        if not lb:
            continue
        try:
            out.append(json.loads(lb.decode("utf-8", "replace")))
        except (ValueError, TypeError):
            continue
    return out


def _parse_session(path):
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        head = fh.read(_HEAD_BYTES)
        has_more = size > len(head)
        message_count = head.count(_MSG_MARKER)
        tail_buf = b""
        while True:
            chunk = fh.read(4 << 20)
            if not chunk:
                break
            message_count += chunk.count(_MSG_MARKER)
            tail_buf = (tail_buf + chunk)[-_TAIL_BYTES:]

    head_objs = _objs_from_chunk(head, drop_first=False, drop_last=has_more)
    tail_objs = _objs_from_chunk(tail_buf, drop_first=True, drop_last=False) if tail_buf else []

    meta = None
    model = None
    model_provider = None
    title = None
    raw_first_ts = None
    raw_last_ts = None
    last_token_info = None

    def scan(objs):
        nonlocal meta, model, model_provider, title, raw_first_ts, raw_last_ts, last_token_info
        for obj in objs:
            ts = obj.get("timestamp")
            if isinstance(ts, str) and ts:
                if raw_first_ts is None:
                    raw_first_ts = ts
                raw_last_ts = ts
            otype = obj.get("type")
            payload = obj.get("payload")
            if not isinstance(payload, dict):
                continue
            if otype == "session_meta":
                meta = payload
                model_provider = payload.get("model_provider")
                if payload.get("model"):
                    model = payload.get("model")
            elif otype == "turn_context":
                if not model and payload.get("model"):
                    model = payload.get("model")
            elif otype == "response_item" and payload.get("type") == "message":
                role = payload.get("role")
                if role in ("user", "assistant"):
                    text = _block_text(payload.get("content"))
                    if title is None and role == "user" and text.strip() and not _is_system_text(text):
                        title = text.strip()[:_TITLE_MAX]
            elif otype == "event_msg" and payload.get("type") == "token_count":
                info = payload.get("info")
                if isinstance(info, dict):
                    last_token_info = info

    scan(head_objs)
    scan(tail_objs)

    if meta is None:
        return None

    created_at = to_iso(meta.get("timestamp")) or to_iso(raw_first_ts)
    updated_at = to_iso(raw_last_ts) or created_at

    project_path = meta.get("cwd")
    project = os.path.basename(project_path) if project_path else None
    session_id = meta.get("id") or os.path.basename(path)

    if not model:
        model = model_provider  # fallback like "openai"

    tokens = _empty_tokens()
    if last_token_info:
        usage = last_token_info.get("total_token_usage")
        if isinstance(usage, dict):
            inp = usage.get("input_tokens", 0) or 0
            out = usage.get("output_tokens", 0) or 0
            cache_read = usage.get("cached_input_tokens", 0) or 0
            reasoning = usage.get("reasoning_output_tokens", 0) or 0
            total = usage.get("total_tokens", 0) or 0
            tokens = {
                "input": inp,
                "output": out,
                "cache_creation": 0,
                "cache_read": cache_read,
                "reasoning": reasoning,
                "total": total,
                "cache_hit_rate": _cache_hit_rate(cache_read, inp, 0),
                "basis": "recorded",
            }

    return {
        "id": session_id,
        "source": SOURCE,
        "title": title or "(untitled)",
        "project_path": project_path,
        "project": project,
        "created_at": created_at,
        "updated_at": updated_at,
        "message_count": message_count,
        "model": model,
        "tokens": tokens,
        "ref": os.path.abspath(path),
    }


def list_sessions():
    """One metadata dict per session (no messages). Never raises for one bad
    session; simply skips it. Lines that can't hold the fields we need are
    skipped before json.loads, so hundreds of rollout files parse quickly."""
    out = []
    for path in _session_files():
        try:
            rec = _parse_session(path)
        except Exception:
            continue
        if rec is not None:
            out.append(rec)
    return out


_MSG_LINE_MARKERS = ('"type":"message"', '"type": "message"',
                     '"type":"reasoning"', '"type": "reasoning"')


def load_messages(session_id, ref):
    """Full ordered transcript for one session, built only from response_item
    message/reasoning items (event_msg duplicates them). Lines that can't be a
    message are skipped before json.loads so giant tool-output blobs in a
    multi-hundred-MB rollout don't get parsed."""
    messages = []
    path = ref
    if not path or not os.path.exists(path):
        return messages

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not any(m in line for m in _MSG_LINE_MARKERS):
                continue
            try:
                obj = json.loads(line)
            except (ValueError, TypeError):
                continue
            if obj.get("type") != "response_item":
                continue
            payload = obj.get("payload")
            if not isinstance(payload, dict):
                continue
            ts = to_iso(obj.get("timestamp"))
            ptype = payload.get("type")

            if ptype == "message":
                role = payload.get("role")
                if role not in ("user", "assistant"):
                    continue
                text = _block_text(payload.get("content"))
                if role == "user" and _is_system_text(text):
                    continue
                messages.append({"role": role, "text": text, "ts": ts, "meta": {}})
            elif ptype == "reasoning":
                messages.append(
                    {"role": "reasoning", "text": _reasoning_text(payload), "ts": ts, "meta": {}}
                )

    return messages
