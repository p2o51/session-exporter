"""Claude Code session parser.

Reads Claude Code session transcripts stored as JSONL files under
``~/.claude/projects/<encoded-folder>/<session-uuid>.jsonl`` and exposes them
through the shared parser contract (``list_sessions`` / ``load_messages``).

Standard library only. No imports from sibling parser modules.
"""

import glob
import json
import os
import re
from collections import Counter

SOURCE = "claude"

# Line "type" values that represent real conversational turns.
_TURN_TYPES = ("user", "assistant")

# Command-message tag stripping helpers.
_CMD_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)
_CMD_NAME_RE = re.compile(r"<command-name>(.*?)</command-name>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")

_TITLE_MAX = 120


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def to_iso(value):
    """Convert epoch-seconds, epoch-millis, or an ISO string to
    ``YYYY-MM-DDTHH:MM:SSZ`` (UTC). Returns None on failure."""
    if value is None:
        return None

    # Numeric epoch (seconds or millis).
    if isinstance(value, (int, float)):
        ts = float(value)
        # Heuristic: treat very large numbers as milliseconds.
        if ts > 1e12:
            ts /= 1000.0
        try:
            import datetime

            dt = datetime.datetime.utcfromtimestamp(ts)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (OverflowError, OSError, ValueError):
            return None

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Numeric string?
        try:
            num = float(s)
        except ValueError:
            num = None
        if num is not None:
            return to_iso(num)

        # Already ISO-ish. Normalize to second precision + trailing Z.
        import datetime

        candidate = s
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            dt = datetime.datetime.fromisoformat(candidate)
        except ValueError:
            # Last resort: chop fractional seconds / timezone and retry.
            m = re.match(
                r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})", s
            )
            if m:
                return "%sT%sZ" % (m.group(1), m.group(2))
            return None
        if dt.tzinfo is not None:
            dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    return None


def _compute_cache_hit_rate(input_t, cache_creation, cache_read, has_cache_read):
    """cache_read / (input + cache_creation + cache_read), guarded."""
    if not has_cache_read:
        return None
    denom = input_t + cache_creation + cache_read
    if denom <= 0:
        return None
    return cache_read / denom


def _iter_lines(path):
    """Yield parsed JSON objects from a JSONL file, skipping bad lines."""
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
    """Return the plain human text from a message.content value, or ''.

    A string passes through. A block list yields the concatenation of
    ``{type:"text"}`` block texts. tool_result / image / other blocks are
    ignored here (used for title extraction)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
        return "".join(parts)
    return ""


def _clean_title(text):
    """Strip command tags, collapse whitespace, trim to _TITLE_MAX."""
    if not text:
        return ""
    s = text
    # Prefer <command-args> when this is a slash command wrapper.
    if "<command-name>" in s or "<command-args>" in s:
        args = _CMD_ARGS_RE.search(s)
        name = _CMD_NAME_RE.search(s)
        chosen = ""
        if args and args.group(1).strip():
            chosen = args.group(1).strip()
        elif name and name.group(1).strip():
            chosen = name.group(1).strip()
        if chosen:
            s = chosen
        else:
            s = _TAG_RE.sub(" ", s)
    # Collapse whitespace to a single line.
    s = " ".join(s.split())
    if len(s) > _TITLE_MAX:
        s = s[:_TITLE_MAX].rstrip()
    return s


def _decode_folder(encoded):
    """Fallback project_path from encoded folder name (lossy)."""
    if not encoded:
        return None
    # Encoded form replaces '/' with '-'; leading '-' -> leading '/'.
    return encoded.replace("-", "/")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def list_sessions():
    """Return one metadata dict per session (no full messages)."""
    pattern = os.path.expanduser("~/.claude/projects/*/*.jsonl")
    sessions = []
    for path in sorted(glob.glob(pattern)):
        try:
            meta = _summarize_session(path)
            if meta is not None:
                sessions.append(meta)
        except Exception:
            # Never raise for one bad session.
            continue
    return sessions


def _summarize_session(path):
    basename = os.path.basename(path)
    session_id = basename[:-6] if basename.endswith(".jsonl") else basename

    encoded_folder = os.path.basename(os.path.dirname(path))

    first_session_id = None
    project_path = None
    created_at = None
    updated_at = None
    message_count = 0
    models = Counter()

    input_t = output_t = cache_creation = cache_read = 0
    cache_creation_5m = cache_creation_1h = 0
    has_cache_read = False

    title = ""
    last_prompt = None

    for obj in _iter_lines(path):
        if not isinstance(obj, dict):
            continue
        ltype = obj.get("type")

        if first_session_id is None and obj.get("sessionId"):
            first_session_id = obj.get("sessionId")

        if project_path is None and obj.get("cwd"):
            project_path = obj.get("cwd")

        # Timestamp bounds.
        iso = to_iso(obj.get("timestamp"))
        if iso is not None:
            if created_at is None or iso < created_at:
                created_at = iso
            if updated_at is None or iso > updated_at:
                updated_at = iso

        if ltype in _TURN_TYPES:
            message_count += 1

        if ltype == "assistant":
            msg = obj.get("message")
            if isinstance(msg, dict):
                model = msg.get("model")
                if model:
                    models[model] += 1
                usage = msg.get("usage")
                if isinstance(usage, dict):
                    input_t += usage.get("input_tokens") or 0
                    output_t += usage.get("output_tokens") or 0
                    cache_creation += (
                        usage.get("cache_creation_input_tokens") or 0
                    )
                    # 5-min vs 1-hour cache writes bill at different multipliers
                    cc = usage.get("cache_creation")
                    if isinstance(cc, dict):
                        cache_creation_5m += cc.get("ephemeral_5m_input_tokens") or 0
                        cache_creation_1h += cc.get("ephemeral_1h_input_tokens") or 0
                    cr = usage.get("cache_read_input_tokens")
                    if cr is not None:
                        cache_read += cr or 0
                        has_cache_read = True

        elif ltype == "user":
            if not title:
                msg = obj.get("message")
                content = msg.get("content") if isinstance(msg, dict) else None
                text = _text_from_content(content)
                cleaned = _clean_title(text)
                if cleaned:
                    title = cleaned

        elif ltype == "last-prompt":
            lp = obj.get("lastPrompt")
            if isinstance(lp, str) and lp.strip():
                last_prompt = lp

    # Title fallback: last-prompt string.
    if not title and last_prompt:
        title = _clean_title(last_prompt)

    if not title:
        title = session_id

    # id resolution.
    sid = session_id or first_session_id or basename

    # project_path fallback via lossy folder decode.
    if not project_path:
        project_path = _decode_folder(encoded_folder)

    project = os.path.basename(project_path) if project_path else None

    # created/updated fallback to file mtime.
    if created_at is None or updated_at is None:
        try:
            mtime_iso = to_iso(os.path.getmtime(path))
        except OSError:
            mtime_iso = None
        if created_at is None:
            created_at = mtime_iso
        if updated_at is None:
            updated_at = mtime_iso

    total = input_t + output_t + cache_creation + cache_read
    tokens = {
        "input": input_t,
        "output": output_t,
        "cache_creation": cache_creation,
        "cache_creation_5m": cache_creation_5m,
        "cache_creation_1h": cache_creation_1h,
        "cache_read": cache_read,
        "reasoning": 0,
        "total": total,
        "cache_hit_rate": _compute_cache_hit_rate(
            input_t, cache_creation, cache_read, has_cache_read
        ),
        "basis": "recorded",
    }

    model = models.most_common(1)[0][0] if models else None

    return {
        "id": sid,
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


def _render_content(content):
    """Render a message.content value to plain text for a transcript line."""
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
            if isinstance(t, str):
                parts.append(t)
        elif btype == "tool_use":
            name = block.get("name") or "?"
            try:
                inp = json.dumps(
                    block.get("input"), ensure_ascii=False, separators=(",", ":")
                )
            except (TypeError, ValueError):
                inp = str(block.get("input"))
            if inp is None:
                inp = ""
            if len(inp) > 500:
                inp = inp[:500]
            parts.append("[tool: %s] %s" % (name, inp))
        elif btype == "tool_result":
            rc = block.get("content")
            rtext = _render_content(rc) if not isinstance(rc, str) else rc
            if rtext is None:
                rtext = ""
            if len(rtext) > 500:
                rtext = rtext[:500]
            parts.append("[tool result] " + rtext)
        elif btype == "thinking":
            th = block.get("thinking") or ""
            parts.append("[thinking] " + th)
        elif btype == "image":
            parts.append("[image]")
        # Unknown block types are ignored.
    return "\n".join(parts)


def load_messages(session_id, ref):
    """Return the full ordered transcript for one session."""
    messages = []
    if not ref or not os.path.exists(ref):
        return messages

    for obj in _iter_lines(ref):
        if not isinstance(obj, dict):
            continue
        ltype = obj.get("type")
        if ltype not in ("user", "assistant", "system"):
            continue

        msg = obj.get("message")
        if isinstance(msg, dict):
            role = msg.get("role") or ltype
            content = msg.get("content")
            model = msg.get("model")
        else:
            # system lines may carry text directly.
            role = ltype
            content = obj.get("content")
            if content is None:
                content = obj.get("message")
            model = None

        text = _render_content(content)
        if not text and isinstance(content, str):
            text = content

        meta = {"sidechain": bool(obj.get("isSidechain"))}
        if model:
            meta["model"] = model

        messages.append(
            {
                "role": role,
                "text": text,
                "ts": to_iso(obj.get("timestamp")),
                "meta": meta,
            }
        )

    return messages
