"""Kimi Code CLI session parser.

Reads session state and Agent wire logs from ``$KIMI_CODE_HOME`` (default
``~/.kimi-code``). Each session has a ``state.json`` plus one ``wire.jsonl``
per main/sub-Agent. ``usage.record`` events expose provider-normalized token
usage, so totals and cache hit rates are recorded values rather than estimates.

Standard library only. No imports from sibling parser modules.
"""

from __future__ import annotations

import glob
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone

SOURCE = "kimi"

_TITLE_MAX = 120
_RESULT_MAX = 1200
_DATA_ROOT = os.path.expanduser(os.environ.get("KIMI_CODE_HOME", "~/.kimi-code"))
_SESSIONS_GLOB = os.path.join(_DATA_ROOT, "sessions", "*", "*", "state.json")
_DEFAULT_TITLES = {"", "new session"}


def to_iso(value):
    """Return an epoch/ISO value as a UTC ISO-8601 string."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 1e11:
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return to_iso(float(text))
        except ValueError:
            pass
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


def _iter_lines(path):
    try:
        fh = open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return
    with fh:
        for line_number, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (TypeError, ValueError):
                continue
            if isinstance(obj, dict):
                yield line_number, obj


def _wire_paths(session_dir):
    return sorted(glob.glob(os.path.join(session_dir, "agents", "*", "wire.jsonl")))


def _trim_title(text):
    clean = " ".join((text or "").split())
    return clean[:_TITLE_MAX].rstrip()


def _human_prompt(text):
    """Strip known host wrappers while leaving ordinary CLI prompts intact."""
    if not isinstance(text, str):
        return ""
    marker = "# User request"
    if marker not in text or not text.lstrip().startswith("# Instructions (read first)"):
        return text
    request = text.rsplit(marker, 1)[1].lstrip("- \n")
    user_turns = re.split(r"(?m)^## user\s*$", request)
    if len(user_turns) > 1:
        request = user_turns[-1]
    request = re.split(r"(?m)^## assistant\s*$", request, maxsplit=1)[0]
    return request.strip() or text


def _json_text(value, limit=500):
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            text = str(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _render_parts(parts):
    if isinstance(parts, str):
        return parts
    if not isinstance(parts, list):
        return ""
    out = []
    for part in parts:
        if isinstance(part, str):
            out.append(part)
            continue
        if not isinstance(part, dict):
            continue
        kind = part.get("type")
        if kind == "text" and isinstance(part.get("text"), str):
            out.append(part["text"])
        elif kind in ("image", "image_url"):
            out.append("[image]")
        elif kind in ("video", "video_url"):
            out.append("[video]")
        elif kind in ("file", "document"):
            name = part.get("name") or part.get("filename")
            out.append("[file%s]" % (": " + str(name) if name else ""))
    return "\n".join(piece for piece in out if piece)


def _render_tool_result(result):
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        return _render_parts(result) or _json_text(result, _RESULT_MAX)
    if not isinstance(result, dict):
        return _json_text(result, _RESULT_MAX)

    output = result.get("output")
    if output is not None:
        text = (
            _render_parts(output)
            if isinstance(output, list)
            else _json_text(output, _RESULT_MAX)
        )
    else:
        text = ""
        for key in ("error", "message", "note"):
            if result.get(key):
                text = _json_text(result[key], _RESULT_MAX)
                break
        if not text:
            text = _json_text(result, _RESULT_MAX)
    if result.get("truncated"):
        text += "\n[truncated]"
    return text if len(text) <= _RESULT_MAX else text[:_RESULT_MAX] + "…"


def _read_state(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            value = json.load(fh)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _cache_hit_rate(input_t, cache_creation, cache_read, has_cache_fields):
    if not has_cache_fields:
        return None
    denominator = input_t + cache_creation + cache_read
    return (cache_read / denominator) if denominator > 0 else None


def list_sessions():
    sessions = []
    for state_path in sorted(glob.glob(_SESSIONS_GLOB)):
        try:
            session = _summarize_session(state_path)
            if session is not None:
                sessions.append(session)
        except Exception:
            continue
    return sessions


def _summarize_session(state_path):
    state = _read_state(state_path)
    session_dir = os.path.dirname(state_path)
    session_id = os.path.basename(session_dir)

    input_t = output_t = cache_creation = cache_read = 0
    has_cache_fields = False
    message_count = 0
    models = Counter()
    fallback_model = None
    first_prompt = ""
    first_event_at = None
    last_event_at = None

    for wire_path in _wire_paths(session_dir):
        for _line_number, obj in _iter_lines(wire_path):
            event_iso = to_iso(obj.get("time") or obj.get("created_at"))
            if event_iso:
                first_event_at = min(first_event_at, event_iso) if first_event_at else event_iso
                last_event_at = max(last_event_at, event_iso) if last_event_at else event_iso

            event_type = obj.get("type")
            if event_type in ("turn.prompt", "turn.steer"):
                text = _human_prompt(_render_parts(obj.get("input")))
                if text.strip():
                    message_count += 1
                    if not first_prompt:
                        first_prompt = _trim_title(text)
            elif event_type == "context.append_loop_event":
                event = obj.get("event")
                if isinstance(event, dict) and event.get("type") == "content.part":
                    part = event.get("part")
                    if isinstance(part, dict) and part.get("type") == "text":
                        if str(part.get("text") or "").strip():
                            message_count += 1
            elif event_type == "usage.record":
                usage = obj.get("usage")
                if not isinstance(usage, dict):
                    continue
                input_t += int(usage.get("inputOther") or 0)
                output_t += int(usage.get("output") or 0)
                cache_read += int(usage.get("inputCacheRead") or 0)
                cache_creation += int(usage.get("inputCacheCreation") or 0)
                has_cache_fields = has_cache_fields or (
                    "inputCacheRead" in usage or "inputCacheCreation" in usage
                )
                if obj.get("model"):
                    models[str(obj["model"])] += 1
            elif event_type == "llm.request":
                fallback_model = obj.get("modelAlias") or obj.get("model") or fallback_model
            elif event_type == "config.update":
                fallback_model = obj.get("modelAlias") or fallback_model

    state_title = _trim_title(str(state.get("title") or ""))
    last_prompt = state.get("lastPrompt")
    if not isinstance(last_prompt, str):
        last_prompt = _render_parts(last_prompt)
    last_prompt = _human_prompt(last_prompt)
    wrapped_title = state_title.startswith("# Instructions (read first)")
    if state_title.lower() in _DEFAULT_TITLES or wrapped_title:
        title = first_prompt or _trim_title(last_prompt) or state_title or session_id
    else:
        title = state_title

    project_path = state.get("workDir")
    project = os.path.basename(project_path.rstrip("/")) if project_path else None
    if project_path == "/" or project == "":
        project = project_path

    created_at = to_iso(state.get("createdAt")) or first_event_at
    updated_at = to_iso(state.get("updatedAt")) or last_event_at or created_at
    if created_at is None or updated_at is None:
        try:
            mtime = to_iso(os.path.getmtime(state_path))
        except OSError:
            mtime = None
        created_at = created_at or mtime
        updated_at = updated_at or mtime

    total = input_t + output_t + cache_creation + cache_read
    model = models.most_common(1)[0][0] if models else fallback_model
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
        "tokens": {
            "input": input_t,
            "output": output_t,
            "cache_creation": cache_creation,
            "cache_read": cache_read,
            "reasoning": 0,
            "total": total,
            "cache_hit_rate": _cache_hit_rate(
                input_t, cache_creation, cache_read, has_cache_fields
            ),
            "basis": "recorded",
        },
        "ref": os.path.abspath(session_dir),
    }


def load_messages(session_id, ref):
    if not ref or not os.path.isdir(ref):
        return []

    ordered = []
    for agent_order, wire_path in enumerate(_wire_paths(ref)):
        agent = os.path.basename(os.path.dirname(wire_path))
        current_model = None
        for line_number, obj in _iter_lines(wire_path):
            event_type = obj.get("type")
            if event_type == "llm.request":
                current_model = obj.get("modelAlias") or obj.get("model") or current_model
                continue
            if event_type == "config.update":
                current_model = obj.get("modelAlias") or current_model
                continue

            role = text = None
            meta = {}
            if agent != "main":
                meta["agent"] = agent

            if event_type in ("turn.prompt", "turn.steer"):
                role = "user"
                text = _human_prompt(_render_parts(obj.get("input")))
                if event_type == "turn.steer":
                    meta["steer"] = True
            elif event_type == "context.append_loop_event":
                event = obj.get("event")
                if not isinstance(event, dict):
                    continue
                loop_type = event.get("type")
                if loop_type == "content.part":
                    part = event.get("part")
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "text":
                        role, text = "assistant", part.get("text")
                    elif part.get("type") in ("think", "thinking"):
                        role = "reasoning"
                        text = part.get("think") or part.get("thinking") or part.get("text")
                    if current_model:
                        meta["model"] = current_model
                elif loop_type == "tool.call":
                    name = event.get("name") or "?"
                    role = "tool"
                    text = "[tool call: %s] %s" % (name, _json_text(event.get("args") or {}))
                    meta["tool"] = name
                elif loop_type == "tool.result":
                    role = "tool"
                    text = "[tool result] " + _render_tool_result(event.get("result"))

            if role and isinstance(text, str) and text.strip():
                raw_time = obj.get("time")
                sort_time = (
                    float(raw_time)
                    if isinstance(raw_time, (int, float))
                    else float("inf")
                )
                ordered.append(
                    (
                        sort_time,
                        agent_order,
                        line_number,
                        {
                            "role": role,
                            "text": text,
                            "ts": to_iso(raw_time),
                            "meta": meta,
                        },
                    )
                )

    ordered.sort(key=lambda item: item[:3])
    return [item[3] for item in ordered]
