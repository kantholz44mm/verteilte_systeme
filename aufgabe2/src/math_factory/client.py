from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import uuid
from typing import Any, Dict, List, Optional

import httpx
import websockets


async def _rpc_call(
    client: httpx.AsyncClient, rpc_url: str, request_id: int, method: str, params: Dict[str, object]
) -> object:
    response = await client.post(
        rpc_url,
        json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
    )
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(f"JSON-RPC error {data['error']['code']}: {data['error']['message']}")
    return data["result"]


async def _wait_for_http(
    client: httpx.AsyncClient, url: str, retries: int = 40, delay: float = 0.5
) -> None:
    last_error: Optional[Exception] = None
    for _ in range(retries):
        try:
            response = await client.get(url)
            response.raise_for_status()
            if response.json().get("status") == "ok":
                return
        except Exception as error:
            last_error = error
            await asyncio.sleep(delay)
    raise RuntimeError(f"HTTP endpoint {url} did not become ready: {last_error}")


async def _connect_websocket_with_retry(
    ws_url: str, retries: int = 40, delay: float = 0.5
):
    last_error: Optional[Exception] = None
    for _ in range(retries):
        try:
            return await websockets.connect(ws_url)
        except Exception as error:
            last_error = error
            await asyncio.sleep(delay)
    raise RuntimeError(f"WebSocket endpoint did not become ready: {last_error}")


class NotificationState:
    def __init__(self) -> None:
        self.messages: List[Dict[str, object]] = []
        self.threshold_event: Optional[Dict[str, object]] = None


async def _watch_notifications(websocket, stop_event: asyncio.Event, state: NotificationState) -> None:
    try:
        async for raw_message in websocket:
            message = json.loads(raw_message)
            state.messages.append(message)
            print(f"[ws] {json.dumps(message)}")
            if message.get("type") == "threshold_exceeded":
                state.threshold_event = message
                stop_event.set()
                return
    except websockets.ConnectionClosed:
        return


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


async def _run_client() -> None:
    args = parse_args()
    if args.terms < 0:
        raise SystemExit("--terms must be non-negative.")

    rest_url = f"http://{args.server_host}:{args.rest_port}/health"
    rpc_url = f"http://{args.server_host}:{args.rpc_port}/rpc"
    rpc_health_url = f"http://{args.server_host}:{args.rpc_port}/health"
    ws_url = f"ws://{args.server_host}:{args.ws_port}/ws"

    session_id = str(uuid.uuid4())
    stop_event = asyncio.Event()
    request_ids = itertools.count(1)
    partial_sums: List[Dict[str, float]] = []

    async with httpx.AsyncClient(timeout=5.0) as client:
        await _wait_for_http(client, rest_url)
        await _wait_for_http(client, rpc_health_url)

        async with await _connect_websocket_with_retry(ws_url) as websocket:
            await websocket.send(
                json.dumps({"action": "register", "session_id": session_id, "threshold": args.threshold})
            )

            notification_state = NotificationState()
            watcher_task = asyncio.create_task(_watch_notifications(websocket, stop_event, notification_state))

            running_sum = 0.0
            try:
                print(f"session_id={session_id}")
                print(f"Calculating e^{args.x} with N={args.terms}")
                for n in range(args.terms + 1):
                    if stop_event.is_set():
                        break

                    numerator = await _rpc_call(
                        client,
                        rpc_url,
                        next(request_ids),
                        "power",
                        {"a": args.x, "b": n, "session_id": session_id},
                    )
                    denominator = await _rpc_call(
                        client,
                        rpc_url,
                        next(request_ids),
                        "factorial",
                        {"a": n, "session_id": session_id},
                    )
                    term = await _rpc_call(
                        client,
                        rpc_url,
                        next(request_ids),
                        "division",
                        {"a": numerator, "b": denominator, "session_id": session_id},
                    )
                    running_sum = float(
                        await _rpc_call(
                            client,
                            rpc_url,
                            next(request_ids),
                            "addition",
                            {"a": running_sum, "b": term, "session_id": session_id},
                        )
                    )

                    partial_sums.append({"n": n, "term": float(term), "sum": running_sum})
                    print(f"n={n:02d} term={float(term):.10f} partial_sum={running_sum:.10f}")

                    if args.new_threshold is not None and n == args.new_threshold_after:
                        await websocket.send(
                            json.dumps(
                                {
                                    "action": "set_threshold",
                                    "session_id": session_id,
                                    "threshold": args.new_threshold,
                                }
                            )
                        )

                    if stop_event.is_set():
                        break
            finally:
                stop_event.set()
                await websocket.close()
                await watcher_task

    print(f"Computed {len(partial_sums)} partial sums.")
    if partial_sums:
        print(f"Latest approximation: {partial_sums[-1]['sum']:.10f}")

    if notification_state.threshold_event:
        print(
            "Calculation stopped because the server reported a threshold violation: "
            f"{json.dumps(notification_state.threshold_event)}"
        )
    else:
        print("Calculation finished without a threshold violation.")


def main() -> None:
    asyncio.run(_run_client())


if __name__ == "__main__":
    main()
