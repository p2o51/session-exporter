"""Tiny stdlib HTTP server: serves the web UI and a small JSON/zip API.

Endpoints
  GET  /                         -> web/index.html
  GET  /styles.css, /app.js      -> static assets
  GET  /api/sessions             -> {status:"ready", sources, sessions, count, generated_at}
                                     or 202 {status:"building"} while the first scan runs
  GET  /api/sessions?refresh=1   -> force a re-scan (blocks)
  GET  /api/session?source=&id=  -> {meta, messages}
  POST /api/export               -> body {format:"raw"|"notion", items:[{source,id}], filter}
                                     -> a .zip download
"""

from __future__ import annotations

import json
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import exporters
import model
import pricing

APP_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(APP_DIR, "web")

_ready = threading.Event()
_build_error: list[str] = []

_STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
}


def _background_build():
    try:
        model.store.index()
    except Exception as e:  # noqa: BLE001
        _build_error.append(str(e))
    finally:
        _ready.set()


class Handler(BaseHTTPRequestHandler):
    server_version = "SessionExporter/1.0"

    # ── helpers ──────────────────────────────────────────────────────────────
    def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _static(self, path):
        name, ctype = _STATIC[path]
        try:
            with open(os.path.join(WEB_DIR, name), "rb") as f:
                data = f.read()
        except OSError:
            self._send(404, {"error": "not found"})
            return
        self._send(200, data, ctype)

    def log_message(self, fmt, *args):  # quieter console
        return

    # ── routing ──────────────────────────────────────────────────────────────
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, qs = parsed.path, urllib.parse.parse_qs(parsed.query)
        if path in _STATIC:
            return self._static(path)
        if path == "/api/sessions":
            return self._api_sessions(qs)
        if path == "/api/session":
            return self._api_session(qs)
        if path == "/api/pricing":
            return self._send(200, {"models": pricing.table()})
        return self._send(404, {"error": "not found"})

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/export":
            return self._api_export()
        return self._send(404, {"error": "not found"})

    # ── API ──────────────────────────────────────────────────────────────────
    def _api_sessions(self, qs):
        if qs.get("reprice", ["0"])[0] == "1" and _ready.is_set():
            return self._send(200, {"status": "ready", **model.store.reprice()})
        if qs.get("refresh", ["0"])[0] == "1":
            data = model.store.index(refresh=True)
            _ready.set()
            return self._send(200, {"status": "ready", **data})
        if not _ready.is_set():
            return self._send(202, {"status": "building"})
        if _build_error:
            return self._send(500, {"status": "error", "error": _build_error[0]})
        return self._send(200, {"status": "ready", **model.store.index()})

    def _api_session(self, qs):
        source = (qs.get("source") or [""])[0]
        sid = (qs.get("id") or [""])[0]
        meta = model.store.get_session(source, sid)
        if not meta:
            return self._send(404, {"error": "session not found"})
        messages = model.store.load_messages(source, sid)
        return self._send(200, {"meta": meta, "messages": messages})

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            return {}

    def _api_export(self):
        body = self._read_json_body()
        fmt = body.get("format", "raw")
        want = body.get("items", [])
        filter_meta = body.get("filter", {})

        items = []
        for it in want:
            meta = model.store.get_session(it.get("source"), it.get("id"))
            if not meta:
                continue
            messages = model.store.load_messages(it["source"], it["id"])
            items.append({"meta": meta, "messages": messages})

        if not items:
            return self._send(400, {"error": "no matching sessions to export"})

        if fmt == "notion":
            blob = exporters.build_notion_zip(items, filter_meta)
            fname = "sessions-notion.zip"
        else:
            blob = exporters.build_raw_zip(items, filter_meta)
            fname = "sessions-export.zip"

        self._send(200, blob, "application/zip",
                   extra={"Content-Disposition": f'attachment; filename="{fname}"'})


def serve(host="127.0.0.1", port=8765):
    threading.Thread(target=_background_build, daemon=True).start()
    httpd = ThreadingHTTPServer((host, port), Handler)
    return httpd
