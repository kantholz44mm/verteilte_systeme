from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse

from .rpc import process_jsonrpc_bytes_with_notifications
from .schemas import OperationListResponse, OperationResponse, OperationUpdateRequest
from .state import MathFactoryState


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def add(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[session_id] = websocket

    async def remove(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if self._connections.get(session_id) is websocket:
                self._connections.pop(session_id, None)

    async def broadcast(self, session_id: str, payload: Dict[str, Any]) -> None:
        async with self._lock:
            websocket = self._connections.get(session_id)

        if websocket is None:
            return

        try:
            await websocket.send_json(payload)
        except Exception:
            await self.remove(session_id, websocket)

def create_rest_app(state: MathFactoryState) -> FastAPI:
    app = FastAPI(
        title="Math Factory REST API",
        version="1.0.0",
        description="REST API to manage enabled operations and their costs.",
    )

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/operations", response_model=OperationListResponse)
    async def list_operations() -> OperationListResponse:
        operations = [OperationResponse(**operation) for operation in state.list_operations()]
        return OperationListResponse(operations=operations)

    @app.get("/operations/{name}", response_model=OperationResponse)
    async def get_operation(name: str) -> OperationResponse:
        try:
            return OperationResponse(**state.get_operation(name))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Unknown operation.") from error

    @app.patch("/operations/{name}", response_model=OperationResponse)
    @app.put("/operations/{name}", response_model=OperationResponse)
    async def update_operation(name: str, update: OperationUpdateRequest) -> OperationResponse:
        try:
            updated = state.update_operation(name, **update.model_dump(exclude_none=True))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Unknown operation.") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return OperationResponse(**updated)

    return app


def create_rpc_app(state: MathFactoryState, manager: ConnectionManager) -> FastAPI:
    app = FastAPI(title="Math Factory JSON-RPC API", docs_url=None, openapi_url=None)

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/rpc")
    async def rpc_endpoint(request: Request) -> Response:
        body = await request.body()
        response_body, notifications = process_jsonrpc_bytes_with_notifications(state, body)
        for notification in notifications:
            session_id = notification.get("session_id")
            if isinstance(session_id, str):
                await manager.broadcast(session_id, notification)
        if response_body is None:
            return Response(status_code=204)
        return Response(content=response_body, media_type="application/json")

    return app


def create_ws_app(state: MathFactoryState, manager: ConnectionManager) -> FastAPI:
    app = FastAPI(title="Math Factory WebSocket API", docs_url=None, openapi_url=None)

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        session_id: Optional[str] = None
        try:
            while True:
                message = await websocket.receive_json()
                action = message.get("action")
                next_session_id = message.get("session_id")

                if action not in {"register", "set_threshold", "ping"}:
                    await websocket.send_json({"type": "error", "message": "Unknown WebSocket action."})
                    continue

                if action == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                if not isinstance(next_session_id, str) or not next_session_id.strip():
                    await websocket.send_json({"type": "error", "message": "'session_id' must be a non-empty string."})
                    continue

                if session_id and session_id != next_session_id:
                    await manager.remove(session_id, websocket)

                session_id = next_session_id
                await manager.add(session_id, websocket)

                if action == "register":
                    snapshot = dict(state._get_or_create_session(session_id))
                    await websocket.send_json({"type": "registered", **snapshot})

                if "threshold" in message:
                    try:
                        _, notifications = state.set_threshold_with_notifications(session_id, int(message["threshold"]))
                    except ValueError as error:
                        await websocket.send_json({"type": "error", "message": str(error)})
                        continue
                    for notification in notifications:
                        notify_session_id = notification.get("session_id")
                        if isinstance(notify_session_id, str):
                            await manager.broadcast(notify_session_id, notification)
        except WebSocketDisconnect:
            pass
        finally:
            if session_id:
                await manager.remove(session_id, websocket)

    return app


def _build_server(app: FastAPI, host: str, port: int) -> uvicorn.Server:
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
            lifespan="off",
        )
    )
    server.install_signal_handlers = lambda: None
    return server


async def _serve_all() -> None:
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    rest_port = int(os.getenv("REST_PORT", "8080"))
    rpc_port = int(os.getenv("RPC_PORT", "8081"))
    ws_port = int(os.getenv("WS_PORT", "8082"))

    state = MathFactoryState()
    manager = ConnectionManager()

    rest_app = create_rest_app(state)
    rpc_app = create_rpc_app(state, manager)
    ws_app = create_ws_app(state, manager)

    print(f"REST server listening on http://{host}:{rest_port}")
    print(f"JSON-RPC server listening on http://{host}:{rpc_port}/rpc")
    print(f"WebSocket server listening on ws://{host}:{ws_port}/ws")

    servers = [
        _build_server(rest_app, host, rest_port),
        _build_server(rpc_app, host, rpc_port),
        _build_server(ws_app, host, ws_port),
    ]

    await asyncio.gather(*(server.serve() for server in servers))


def main() -> None:
    try:
        asyncio.run(_serve_all())
    except KeyboardInterrupt:
        print("Shutting down Math Factory services...")


if __name__ == "__main__":
    main()
