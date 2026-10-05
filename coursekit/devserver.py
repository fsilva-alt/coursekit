"""`coursekit dev`: rebuild on change and live-reload the browser (standard library only)."""

from __future__ import annotations

import functools
import os
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, List

EVENTS_PATH = "/__coursekit/events"
SKIP_DIRS = {"dist", "__pycache__", "node_modules"}   # plus every folder starting with "."


class Reloader:
    def __init__(self) -> None:
        self.version = 0
        self.cond = threading.Condition()

    def bump(self) -> None:
        with self.cond:
            self.version += 1
            self.cond.notify_all()


def _snapshot(paths: List[Path]) -> Dict[str, float]:
    stamps: Dict[str, float] = {}
    for base in paths:
        if base.is_file():
            stamps[str(base)] = base.stat().st_mtime
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS]
            for name in filenames:
                p = os.path.join(dirpath, name)
                try:
                    stamps[p] = os.stat(p).st_mtime
                except OSError:
                    pass
    return stamps


def serve(out_dir: Path, course_dir: Path, extra_watch: List[Path], rebuild: Callable[[], object],
          host: str, port: int, open_browser: bool) -> None:
    """Serve `out_dir` (holding the dev build's index.html) and rebuild when sources change."""
    reloader = Reloader()

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args):  # keep the console for build output
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self):
            if self.path != EVENTS_PATH:
                return super().do_GET()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            seen = reloader.version
            try:
                while True:
                    with reloader.cond:
                        reloader.cond.wait(timeout=15)
                        version = reloader.version
                    message = b"data: reload\n\n" if version != seen else b": ping\n\n"
                    seen = version
                    self.wfile.write(message)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

    out_dir.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), functools.partial(Handler, directory=str(out_dir)))
    server.daemon_threads = True
    watched = [course_dir, *extra_watch]

    def watch() -> None:
        stamps = _snapshot(watched)
        while True:
            time.sleep(0.5)
            current = _snapshot(watched)
            if current != stamps:
                time.sleep(0.15)  # let editors finish writing
                rebuild()
                stamps = _snapshot(watched)
                reloader.bump()

    threading.Thread(target=watch, daemon=True).start()
    url = f"http://{host}:{port}/"
    print(f"\n  Preview at {url}  (rebuilds and reloads when you save; Ctrl+C to stop)\n")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
    finally:
        server.server_close()
