from __future__ import annotations

import json
import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Tuple

from .rpc import process_jsonrpc_bytes
from .state import MathFactoryState, UnknownOperationError
from .websocket import ThreadedWebSocketServer, WebSocketRequestHandler


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = PROJECT_ROOT / "openapi.json"


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def _make_rest_handler(openapi_path: Path):
    class RestHandler(BaseHTTPRequestHandler):
        server_version = "MathFactoryREST/1.0"

        def do_GET(self) -> None:
            path, operation_name = self._resolve_path()
            if path == "/":
                self._send_html(HTTPStatus.OK, self._docs_html())
                return
            if path == "/docs":
                self._send_html(HTTPStatus.OK, self._docs_html())
                return
            if path == "/health":
                self._send_json(HTTPStatus.OK, {"status": "ok"})
                return
            if path == "/openapi.json":
                self._send_bytes(HTTPStatus.OK, openapi_path.read_bytes(), "application/json")
                return
            if path == "/operations":
                self._send_json(HTTPStatus.OK, {"operations": self.server.state.list_operations()})
                return
            if operation_name:
                try:
                    self._send_json(HTTPStatus.OK, self.server.state.get_operation(operation_name))
                except UnknownOperationError:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown operation."})
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Resource not found."})

        def do_PATCH(self) -> None:
            self._handle_operation_update()

        def do_PUT(self) -> None:
            self._handle_operation_update()

        def log_message(self, format: str, *args) -> None:
            return

        def _handle_operation_update(self) -> None:
            _, operation_name = self._resolve_path()
            if not operation_name:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown operation."})
                return

            payload = self._read_json_body()
            if payload is None:
                return

            try:
                updated = self.server.state.update_operation(
                    operation_name,
                    cost=payload.get("cost"),
                    enabled=payload.get("enabled"),
                )
            except UnknownOperationError:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown operation."})
                return
            except ValueError as error:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return

            self._send_json(HTTPStatus.OK, updated)

        def _resolve_path(self) -> Tuple[str, str]:
            path = self.path.split("?", 1)[0]
            if path.startswith("/operations/"):
                return "/operations/{name}", path.rsplit("/", 1)[-1]
            return path, ""

        def _read_json_body(self):
            length = int(self.headers.get("Content-Length", "0"))
            data = self.rfile.read(length) if length else b"{}"
            try:
                return json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Request body must contain valid JSON."})
                return None

        def _send_json(self, status: HTTPStatus, payload: Dict[str, object]) -> None:
            body = json.dumps(payload, indent=2).encode("utf-8")
            self._send_bytes(status, body, "application/json")

        def _send_html(self, status: HTTPStatus, html: str) -> None:
            self._send_bytes(status, html.encode("utf-8"), "text/html; charset=utf-8")

        def _send_bytes(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        @staticmethod
        def _docs_html() -> str:
            return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Math Factory REST API</title>
  </head>
  <body>
    <h1>Math Factory REST API</h1>
    <p>The OpenAPI description is available at <a href="/openapi.json">/openapi.json</a>.</p>
    <h2>Available endpoints</h2>
    <ul>
      <li><code>GET /health</code></li>
      <li><code>GET /operations</code></li>
      <li><code>GET /operations/{name}</code></li>
      <li><code>PATCH /operations/{name}</code></li>
      <li><code>PUT /operations/{name}</code></li>
    </ul>
    <h2>Example</h2>
    <pre>curl -X PATCH http://localhost:8080/operations/power \
  -H 'Content-Type: application/json' \
  -d '{"cost": 900, "enabled": true}'</pre>
  </body>
</html>
"""

    return RestHandler


class RpcHandler(BaseHTTPRequestHandler):
    server_version = "MathFactoryRPC/1.0"

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path not in {"/", "/rpc"}:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Resource not found."})
            return

        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length)
        response = process_jsonrpc_bytes(self.server.state, payload)
        if response is None:
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Resource not found."})

    def log_message(self, format: str, *args) -> None:
        return

    def _send_json(self, status: HTTPStatus, payload: Dict[str, object]) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _start_thread(server, label: str) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, name=label, daemon=True)
    thread.start()
    return thread


def main() -> None:
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    rest_port = int(os.getenv("REST_PORT", "8080"))
    rpc_port = int(os.getenv("RPC_PORT", "8081"))
    ws_port = int(os.getenv("WS_PORT", "8082"))

    state = MathFactoryState()
    rest_server = ReusableThreadingHTTPServer((host, rest_port), _make_rest_handler(OPENAPI_PATH))
    rpc_server = ReusableThreadingHTTPServer((host, rpc_port), RpcHandler)
    ws_server = ThreadedWebSocketServer((host, ws_port), WebSocketRequestHandler)

    rest_server.state = state
    rpc_server.state = state
    ws_server.state = state

    print(f"REST server listening on http://{host}:{rest_port}")
    print(f"JSON-RPC server listening on http://{host}:{rpc_port}/rpc")
    print(f"WebSocket server listening on ws://{host}:{ws_port}/ws")

    threads = [
        _start_thread(rest_server, "rest-server"),
        _start_thread(rpc_server, "rpc-server"),
        _start_thread(ws_server, "ws-server"),
    ]

    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        print("Shutting down Math Factory services...")
    finally:
        rest_server.shutdown()
        rpc_server.shutdown()
        ws_server.shutdown()
        rest_server.server_close()
        rpc_server.server_close()
        ws_server.server_close()


if __name__ == "__main__":
    main()

