from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from taskcard.core import TaskCardError, TaskStore


WEB_ROOT = Path(__file__).resolve().parent / "web"


class Handler(BaseHTTPRequestHandler):
    store: TaskStore

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[taskcard] {self.address_string()} {fmt % args}")

    def send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, value: object) -> None:
        self.send_bytes(
            status,
            json.dumps(value, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.send_json(HTTPStatus.OK, {"ok": True, "service": "taskcard-v1"})
        if path == "/api/cards":
            return self.send_json(HTTPStatus.OK, self.store.list_cards())
        if path.startswith("/api/cards/"):
            card_id = unquote(path.removeprefix("/api/cards/"))
            try:
                return self.send_json(HTTPStatus.OK, self.store.get(card_id))
            except TaskCardError as exc:
                return self.send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": str(exc)})

        files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
        }
        target = files.get(path)
        if not target:
            return self.send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
        filename, content_type = target
        self.send_bytes(HTTPStatus.OK, (WEB_ROOT / filename).read_bytes(), content_type)


def serve(store: TaskStore, host: str, port: int) -> None:
    handler = type("TaskCardHandler", (Handler,), {"store": store})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Task Card V1: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

