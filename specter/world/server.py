"""Loopback-only desktop service. Files are selected from explicitly approved roots."""

from __future__ import annotations
import argparse
import heapq
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import signal
import threading
import time
from urllib.parse import urlparse, parse_qs
import webbrowser

from .store import WorldStore

WEB = Path(__file__).with_name("web")


CATALOG_LIMIT = 512
SCAN_LIMIT = 20000


def approved_roots(root_args, replay_path=None):
    """Explicit roots only.

    ``--replay`` selects one initial source; it must not implicitly authorize
    the capture's parent directory for evidence browsing. Callers that want a
    directory browsable must pass it as ``--root`` explicitly.
    """
    return [Path(root).resolve() for root in root_args]


def _bounded_iter(entries, state):
    """Yield at most the remaining scan budget; record exhaustion."""
    for entry in entries:
        if state["scanned"] >= SCAN_LIMIT:
            state["scan_truncated"] = True
            return
        state["scanned"] += 1
        yield entry


def _catalog_walk(root, state):
    """Yield files under root with bounded memory and a bounded scan.

    Each directory is reduced with ``heapq.nsmallest`` so at most
    ``CATALOG_LIMIT`` names are retained even for a flat directory with
    tens of thousands of entries. ``SCAN_LIMIT`` is a separate work bound;
    reaching it marks the result incomplete instead of silently presenting a
    partial scan as complete.
    """
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = heapq.nsmallest(
                CATALOG_LIMIT,
                _bounded_iter(directory.iterdir(), state),
                key=lambda p: p.name,
            )
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    resolved = entry.resolve()
                    if not resolved.is_relative_to(root):
                        continue
                    if resolved.is_dir():
                        continue
                    path = resolved
                elif entry.is_dir():
                    stack.append(entry)
                    continue
                else:
                    path = entry
                if not path.is_file():
                    continue
            except OSError:
                continue
            yield path
            if len(state.get("items", ())) >= CATALOG_LIMIT:
                return
        if state["scan_truncated"]:
            return


def catalog_result(roots):
    """Return catalog items plus explicit completeness metadata."""
    items = []
    state = {"scanned": 0, "scan_truncated": False, "items": items}
    limit_truncated = False
    for root in roots:
        root = Path(root).resolve()
        if not root.is_dir():
            continue
        for p in _catalog_walk(root, state):
            if len(items) >= CATALOG_LIMIT:
                limit_truncated = True
                break
            try:
                if not p.resolve().is_relative_to(root):
                    continue
                replay = p.name.endswith((".raw.csi", ".observations.jsonl"))
                evidence = p.suffix in (".md", ".json") and not p.name.endswith(
                    ".manifest.json"
                )
                if not replay and not evidence:
                    continue
                size = p.stat().st_size
            except OSError:
                continue
            if size > (WorldStore.MAX_BYTES if replay else 256 * 1024):
                continue
            items.append(
                dict(
                    id=str(len(items)),
                    name=p.name,
                    group=root.name,
                    relative=str(p.relative_to(root)),
                    kind="replay" if replay else "evidence",
                    bytes=size,
                    path=p.resolve(),
                )
            )
        if limit_truncated or state["scan_truncated"]:
            break
    # A full cap is treated conservatively as possibly truncated: the
    # catalog must never claim completeness when more entries may exist.
    if len(items) >= CATALOG_LIMIT:
        limit_truncated = True
    return {
        "items": items,
        "limit": CATALOG_LIMIT,
        "scan_limit": SCAN_LIMIT,
        "truncated": bool(limit_truncated or state["scan_truncated"]),
        "limit_truncated": bool(limit_truncated),
        "scan_truncated": bool(state["scan_truncated"]),
    }


def catalog(roots):
    return catalog_result(roots)["items"]


class WorldServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, store, roots):
        super().__init__(address, Handler)
        self.store = store
        self.catalog = catalog_result(roots)
        self.items = self.catalog["items"]
        self.token = secrets.token_urlsafe(32)
        self.started = time.monotonic()
        self.request_slots = threading.BoundedSemaphore(12)

    def process_request(self, request, client_address):
        if not self.request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.request_slots.release()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def reply(self, data, status=200, content="application/json"):
        body = (
            json.dumps(data, allow_nan=False).encode()
            if content == "application/json"
            else data
        )
        self.send_response(status)
        self.send_header("Content-Type", content + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def permitted(self):
        expected = f"127.0.0.1:{self.server.server_port}"
        return (
            self.headers.get("Host") == expected
            and self.headers.get("Origin", "http://" + expected) == "http://" + expected
        )

    def item(self, key, kind):
        for item in self.server.items:
            if item["id"] == key and item["kind"] == kind:
                return item
        raise ValueError("unknown catalog item")

    def do_GET(self):
        if not self.permitted():
            return self.reply({"error": "Loopback host/origin required"}, 403)
        url = urlparse(self.path)
        q = parse_qs(url.query)
        try:
            if url.path == "/api/catalog":
                return self.reply(
                    {
                        **self.server.catalog,
                        "items": [
                            {k: v for k, v in i.items() if k != "path"}
                            for i in self.server.items
                        ],
                    }
                )
            if url.path == "/api/state":
                index = int(q["index"][0]) if "index" in q else None
                data = self.server.store.snapshot(
                    index, q.get("source", [None])[0], q.get("q", [""])[0]
                )
                data["service"] = {
                    "state": "RUNNING",
                    "uptime_seconds": round(time.monotonic() - self.server.started, 1),
                    "transport": "loopback HTTP",
                    "acquisition": "not opened",
                }
                return self.reply(data)
            if url.path == "/api/evidence":
                item = self.item(q.get("id", [""])[0], "evidence")
                if item["path"].stat().st_size > 256 * 1024:
                    raise ValueError("evidence exceeds size limit")
                return self.reply(
                    {
                        "name": item["name"],
                        "content": item["path"].read_text(errors="replace"),
                        "interpretation": "Source artifact, not independently validated by WORLD",
                    }
                )
            files = {
                "/": ("index.html", "text/html"),
                "/app.js": ("app.js", "text/javascript"),
                "/style.css": ("style.css", "text/css"),
            }
            if url.path not in files:
                return self.reply({"error": "Not found"}, 404)
            name, mime = files[url.path]
            raw = (
                (WEB / name)
                .read_bytes()
                .replace(b"__TOKEN__", self.server.token.encode())
            )
            return self.reply(raw, content=mime)
        except (ValueError, OSError) as exc:
            return self.reply({"error": str(exc)}, 400)

    def do_POST(self):
        if (
            not self.permitted()
            or self.headers.get("X-Specter-Token") != self.server.token
        ):
            return self.reply({"error": "Local session token required"}, 403)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096:
                raise ValueError("request exceeds limit or is empty")
            d = json.loads(self.rfile.read(size))
            if not isinstance(d, dict):
                raise ValueError("object required")
            if self.path == "/api/session":
                item = self.item(d.get("id"), "replay")
                self.server.store.load(item["path"])
            elif self.path == "/api/control":
                self.server.store.control(d.get("action"), d.get("value"))
            elif self.path == "/api/shutdown":
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                return self.reply({"error": "Unknown command"}, 404)
            return self.reply({"ok": True})
        except (ValueError, OSError, RuntimeError) as exc:
            return self.reply({"error": str(exc)}, 400)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="SPECTER-WORLD local desktop research command center"
    )
    p.add_argument(
        "--root",
        action="append",
        default=[],
        help="approved recordings/evidence directory (repeatable)",
    )
    p.add_argument(
        "--replay",
        help="initial preserved capture; pass --root explicitly to browse evidence",
    )
    p.add_argument(
        "--port", type=int, default=0, help="loopback port; default chooses a free port"
    )
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--max-records", type=int, default=250_000)
    a = p.parse_args(argv)
    store = WorldStore(a.max_records)
    roots = approved_roots(a.root, a.replay)
    try:
        server = WorldServer(("127.0.0.1", a.port), store, roots)
        if a.replay:
            store.load(a.replay)
        url = f"http://127.0.0.1:{server.server_port}"
        print(f"SPECTER-WORLD {url} — local only; no hardware acquisition", flush=True)
        if not a.no_browser:
            webbrowser.open(url)

        def stop(*_):
            threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGTERM, stop)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        store.close()
    return 0
