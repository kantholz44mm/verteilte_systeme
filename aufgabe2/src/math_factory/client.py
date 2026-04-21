from __future__ import annotations

import argparse
import itertools
import json
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Dict, List, Optional

from .websocket import SimpleWebSocketClient


def _rpc_call(rpc_url: str, request_id: int, method: str, params: Dict[str, object]) -> object:
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    ).encode("utf-8")
    request = urllib.request.Request(
        rpc_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        data = json.loads(response.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(f"JSON-RPC error {data['error']['code']}: {data['error']['message']}")
    return data["result"]


def _wait_for_http(url: str, retries: int = 40, delay: float = 0.5) -> None:
    last_error: Optional[Exception] = None
    for _ in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except Exception as error:
            last_error = error
            time.sleep(delay)
    raise RuntimeError(f"HTTP endpoint {url} did not become ready: {last_error}")


def _connect_websocket_with_retry(
    websocket: SimpleWebSocketClient, retries: int = 40, delay: float = 0.5
) -> None:
    last_error: Optional[Exception] = None
    for _ in range(retries):
        try:
            websocket.connect()
            return
        except Exception as error:
            last_error = error
            time.sleep(delay)
    raise RuntimeError(f"WebSocket endpoint did not become ready: {last_error}")


class NotificationWatcher(threading.Thread):
    def __init__(self, websocket: SimpleWebSocketClient, stop_event: threading.Event) -> None:
        super().__init__(daemon=True)
        self._websocket = websocket
        self._stop_event = stop_event
        self.messages: List[Dict[str, object]] = []
        self.threshold_event: Optional[Dict[str, object]] = None

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                message = self._websocket.receive_json(timeout=0.2)
            except socket.timeout:
                continue
            except OSError:
                return

            if message is None:
                return

            self.messages.append(message)
            print(f"[ws] {json.dumps(message)}")
            if message.get("type") == "threshold_exceeded":
                self.threshold_event = message
                self._stop_event.set()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Taylor-series client for the Math Factory server.")
    parser.add_argument("--server-host", default="localhost", help="Math Factory server host name.")
    parser.add_argument("--rest-port", type=int, default=8080, help="REST port of the server.")
    parser.add_argument("--rpc-port", type=int, default=8081, help="JSON-RPC port of the server.")
    parser.add_argument("--ws-port", type=int, default=8082, help="WebSocket port of the server.")
    parser.add_argument("--x", type=float, default=1.0, help="Input value x for e^x.")
    parser.add_argument("--terms", type=int, default=8, help="Number of Taylor terms N.")
    parser.add_argument(
        "--threshold",
        type=int,
        default=2500,
        help="Cost threshold that is sent to the server via WebSocket.",
    )
    parser.add_argument(
        "--new-threshold",
        type=int,
        default=None,
        help="Optional new threshold that should be sent while the calculation is running.",
    )
    parser.add_argument(
        "--new-threshold-after",
        type=int,
        default=2,
        help="Iteration after which --new-threshold should be sent.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.terms < 0:
        raise SystemExit("--terms must be non-negative.")

    rest_url = f"http://{args.server_host}:{args.rest_port}/health"
    rpc_url = f"http://{args.server_host}:{args.rpc_port}/rpc"
    rpc_health_url = f"http://{args.server_host}:{args.rpc_port}/health"

    _wait_for_http(rest_url)
    _wait_for_http(rpc_health_url)

    session_id = str(uuid.uuid4())
    stop_event = threading.Event()
    request_ids = itertools.count(1)
    partial_sums: List[Dict[str, float]] = []

    websocket = SimpleWebSocketClient(args.server_host, args.ws_port)
    _connect_websocket_with_retry(websocket)
    websocket.send_json({"action": "register", "session_id": session_id, "threshold": args.threshold})

    watcher = NotificationWatcher(websocket, stop_event)
    watcher.start()

    running_sum = 0.0
    try:
        print(f"session_id={session_id}")
        print(f"Calculating e^{args.x} with N={args.terms}")
        for n in range(args.terms + 1):
            if stop_event.is_set():
                break

            numerator = _rpc_call(
                rpc_url,
                next(request_ids),
                "power",
                {"a": args.x, "b": n, "session_id": session_id},
            )
            denominator = _rpc_call(
                rpc_url,
                next(request_ids),
                "factorial",
                {"a": n, "session_id": session_id},
            )
            term = _rpc_call(
                rpc_url,
                next(request_ids),
                "division",
                {"a": numerator, "b": denominator, "session_id": session_id},
            )
            running_sum = float(
                _rpc_call(
                    rpc_url,
                    next(request_ids),
                    "addition",
                    {"a": running_sum, "b": term, "session_id": session_id},
                )
            )

            partial_sums.append({"n": n, "term": float(term), "sum": running_sum})
            print(f"n={n:02d} term={float(term):.10f} partial_sum={running_sum:.10f}")

            if args.new_threshold is not None and n == args.new_threshold_after:
                websocket.send_json(
                    {
                        "action": "set_threshold",
                        "session_id": session_id,
                        "threshold": args.new_threshold,
                    }
                )

            if stop_event.is_set():
                break
    finally:
        stop_event.set()
        watcher.join(timeout=1)
        websocket.close()

    print(f"Computed {len(partial_sums)} partial sums.")
    if partial_sums:
        print(f"Latest approximation: {partial_sums[-1]['sum']:.10f}")

    if watcher.threshold_event:
        print(
            "Calculation stopped because the server reported a threshold violation: "
            f"{json.dumps(watcher.threshold_event)}"
        )
    else:
        print("Calculation finished without a threshold violation.")


if __name__ == "__main__":
    main()
