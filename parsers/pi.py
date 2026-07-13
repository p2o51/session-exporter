"""Pi Agent session parser.

Reads Pi Agent transcripts stored as JSONL under
``~/.pi/agent/sessions/<encoded-cwd>/<timestamp>_<uuid>.jsonl``.

Each file starts with a ``type:"session"`` header (id, cwd, timestamp), then
a stream of ``message`` / ``model_change`` / … events. Assistant turns carry
recorded ``usage`` with input / output / cacheRead / cacheWrite.

Standard library only. No imports from sibling parser modules.
"""

from __future__ import annotations

import glob
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone

SOURCE = "pi"

_TITLE_MAX = 120
_SESSIONS_GLOB = os.path.expanduser("~/.pi/agent/sessions/**/*.jsonl")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def to_iso(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        num = float(value)
        if num > 1e12:
            num /= 1000.0
        try:
            return datetime.fromtimestamp(num, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return to_iso(float(s))
        except ValueError:
            pass
        try:
            iso = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            m = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})", s)
            if m:
                return "%sT%sZ" % (m.group(1), m.group(2))
            return None
    return None


def _compute_cache_hit_rate(input_t, cache_creation, cache_read, has_cache_read):
    if not has_cache_read:
        return None
    denom = input_t + cache_creation + cache_read
    if denom <= 0:
        return None
    return cache_read / denom


def _iter_lines(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except (ValueError, TypeError):
                continue


def _text_from_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
        return "".join(parts)
    return ""


def _trim_title(text):
    s = " ".join((text or "").split())
    if len(s) > _TITLE_MAX:
        s = s[:_TITLE_MAX].rstrip()
    return s


def _render_content(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            t = block.get("text")
            if isinstance(t, str) and t.strip():
                parts.append(t)
        elif btype == "thinking":
            th = block.get("thinking") or block.get("text") or ""
            if th:
                parts.append("[thinking] " + th)
        elif btype == "toolCall":
            name = block.get("name") or block.get("toolName") or "?"
            args = block.get("arguments")
            if args is None:
                args = block.get("input")
            try:
                inp = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
            except (TypeError, ValueError):
                inp = str(args)
            if inp and len(inp) > 500:
                inp = inp[:500]
            parts.append("[tool: %s] %s" % (name, inp or ""))
        elif btype == "image":
            parts.append("[image]")
        elif btype == "toolResult":
            rc = block.get("content")
            rtext = _render_content(rc) if not isinstance(rc, str) else rc
            if rtext and len(rtext) > 500:
                rtext = rtext[:500]
            parts.append("[tool result] " + (rtext or ""))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_sessions():
    sessions = []
    for path in sorted(glob.glob(_SESSIONS_GLOB, recursive=True)):
        try:
            meta = _summarize_session(path)
            if meta is not None:
                sessions.append(meta)
        except Exception:
            continue
    return sessions


def _summarize_session(path):
    session_id = None
    project_path = None
    created_at = None
    updated_at = None
    message_count = 0
    models = Counter()
    title = ""

    input_t = output_t = cache_creation = cache_read = 0
    has_cache_read = False
    current_model = None

    for obj in _iter_lines(path):
        if not isinstance(obj, dict):
            continue
        ltype = obj.get("type")

        iso = to_iso(obj.get("timestamp"))
        if iso is not None:
            if created_at is None or iso < created_at:
                created_at = iso
            if updated_at is None or iso > updated_at:
                updated_at = iso

        if ltype == "session":
            session_id = obj.get("id") or session_id
            if obj.get("cwd"):
                project_path = obj.get("cwd")
            continue

        if ltype == "model_change":
            mid = obj.get("modelId") or obj.get("model")
            if mid:
                current_model = mid
                models[mid] += 1
            continue

        if ltype != "message":
            continue

        msg = obj.get("message")
        if not isinstance(msg, dict):
            continue

        role = msg.get("role") or ""
        if role in ("user", "assistant", "toolResult", "tool", "system"):
            message_count += 1

        model = msg.get("model") or current_model
        if model and role == "assistant":
            models[model] += 1

        if role == "user" and not title:
            cleaned = _trim_title(_text_from_content(msg.get("content")))
            if cleaned:
                title = cleaned

        if role == "assistant":
            usage = msg.get("usage")
            if isinstance(usage, dict):
                input_t += int(usage.get("input") or 0)
                output_t += int(usage.get("output") or 0)
                cw = usage.get("cacheWrite")
                if cw is not None:
                    cache_creation += int(cw or 0)
                cr = usage.get("cacheRead")
                if cr is not None:
                    cache_read += int(cr or 0)
                    has_cache_read = True

        msg_ts = to_iso(msg.get("timestamp"))
        if msg_ts is not None:
            if created_at is None or msg_ts < created_at:
                created_at = msg_ts
            if updated_at is None or msg_ts > updated_at:
                updated_at = msg_ts

    if not session_id:
        base = os.path.basename(path)
        # filename: <timestamp>_<uuid>.jsonl
        if "_" in base and base.endswith(".jsonl"):
            session_id = base[base.find("_") + 1 : -6]
        else:
            session_id = base[:-6] if base.endswith(".jsonl") else base

    if not title:
        title = session_id

    if created_at is None or updated_at is None:
        try:
            mtime_iso = to_iso(os.path.getmtime(path))
        except OSError:
            mtime_iso = None
        if created_at is None:
            created_at = mtime_iso
        if updated_at is None:
            updated_at = mtime_iso

    project = os.path.basename(project_path.rstrip("/")) if project_path else None
    if project_path == "/" or project == "":
        project = project_path

    total = input_t + output_t + cache_creation + cache_read
    tokens = {
        "input": input_t,
        "output": output_t,
        "cache_creation": cache_creation,
        "cache_read": cache_read,
        "reasoning": 0,
        "total": total,
        "cache_hit_rate": _compute_cache_hit_rate(
            input_t, cache_creation, cache_read, has_cache_read
        ),
        "basis": "recorded",
    }
    model = models.most_common(1)[0][0] if models else current_model

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


def load_messages(session_id, ref):
    messages = []
    if not ref or not os.path.exists(ref):
        return messages

    for obj in _iter_lines(ref):
        if not isinstance(obj, dict) or obj.get("type") != "message":
            continue
        msg = obj.get("message")
        if not isinstance(msg, dict):
            continue

        role = msg.get("role") or "assistant"
        content = msg.get("content")
        text = _render_content(content)

        # toolResult role → tool
        if role == "toolResult":
            role = "tool"
            if not text:
                # Sometimes result lives on the envelope.
                text = _render_content(obj.get("content")) or str(msg.get("result") or "")
                if text and len(text) > 800:
                    text = text[:800]
                if text:
                    text = "[tool result] " + text

        if not text.strip():
            continue

        # Split thinking into a separate reasoning turn when present alone
        # alongside assistant text — keep inline via [thinking] for simplicity.
        meta = {}
        model = msg.get("model")
        if model:
            meta["model"] = model
        if msg.get("provider"):
            meta["provider"] = msg.get("provider")

        messages.append(
            {
                "role": role if role in ("user", "assistant", "system", "tool", "reasoning") else "assistant",
                "text": text,
                "ts": to_iso(msg.get("timestamp") or obj.get("timestamp")),
                "meta": meta,
            }
        )

    return messages
