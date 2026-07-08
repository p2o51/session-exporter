#!/usr/bin/env python3
"""Session Exporter — browse & export your Claude Code / Codex / Cursor history.

Run:  python3 app.py            (opens http://127.0.0.1:8765 in your browser)
      python3 app.py --port 9000 --no-open
"""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser

import server


def main() -> int:
    ap = argparse.ArgumentParser(description="Browse & export AI coding session history.")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-open", action="store_true", help="don't auto-open the browser")
    args = ap.parse_args()

    try:
        httpd = server.serve(args.host, args.port)
    except OSError as e:
        print(f"✗ could not bind {args.host}:{args.port} — {e}")
        print("  try a different port:  python3 app.py --port 9000")
        return 1

    url = f"http://{args.host}:{args.port}"
    print("┌──────────────────────────────────────────────────┐")
    print("│  Session Exporter                                 │")
    print(f"│  → {url:<45}│")
    print("│  (indexing your sessions in the background…)      │")
    print("│  Press Ctrl+C to stop.                            │")
    print("└──────────────────────────────────────────────────┘")

    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n· stopping…")
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
