from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field


def _model_payload(model: BaseModel) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


class OperationEvent(BaseModel):
    app_id: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    cost: int = Field(ge=0)
    instance_id: str = Field(min_length=1)
    request_id: Optional[str] = None
    result: Optional[Any] = None


class ThresholdRequest(BaseModel):
    threshold: int = Field(ge=0)


@dataclass(frozen=True)
class AppSnapshot:
    app_id: str
    total_cost: int
    threshold: Optional[int]
    threshold_exceeded: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_id": self.app_id,
            "total_cost": self.total_cost,
            "threshold": self.threshold,
            "threshold_exceeded": self.threshold_exceeded,
        }


class DataManagerStore:
    """Writes Ops DB and Cust DB changes in one transaction.

    SQLite is used for the local exercise runtime. The connection attaches two
    separate database files and commits both writes atomically.
    """

    def __init__(self, ops_db_path: str, cust_db_path: str) -> None:
        self.ops_db_path = Path(ops_db_path)
        self.cust_db_path = Path(cust_db_path)
        self.ops_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cust_db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("ATTACH DATABASE ? AS ops", (str(self.ops_db_path),))
        connection.execute("ATTACH DATABASE ? AS cust", (str(self.cust_db_path),))
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ops.operation_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    cost INTEGER NOT NULL,
                    instance_id TEXT NOT NULL,
                    request_id TEXT,
                    result TEXT,
                    created_at_ms INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cust.applications (
                    app_id TEXT PRIMARY KEY,
                    total_cost INTEGER NOT NULL DEFAULT 0,
                    threshold INTEGER,
                    threshold_exceeded INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cust.charge_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    cost INTEGER NOT NULL,
                    instance_id TEXT NOT NULL,
                    request_id TEXT,
                    created_at_ms INTEGER NOT NULL
                )
                """
            )

    async def record_operation(self, event: OperationEvent) -> Dict[str, Any]:
        async with self._lock:
            with self._connect() as connection:
                connection.isolation_level = None
                connection.execute("BEGIN IMMEDIATE")
                try:
                    created_at_ms = int(time.time() * 1000)
                    payload = _model_payload(event)
                    connection.execute(
                        """
                        INSERT INTO ops.operation_log
                            (app_id, operation, cost, instance_id, request_id, result, created_at_ms)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event.app_id,
                            event.operation,
                            event.cost,
                            event.instance_id,
                            event.request_id,
                            repr(payload.get("result")),
                            created_at_ms,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO cust.applications (app_id, total_cost, threshold, threshold_exceeded)
                        VALUES (?, 0, NULL, 0)
                        ON CONFLICT(app_id) DO NOTHING
                        """,
                        (event.app_id,),
                    )
                    connection.execute(
                        """
                        INSERT INTO cust.charge_log
                            (app_id, operation, cost, instance_id, request_id, created_at_ms)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event.app_id,
                            event.operation,
                            event.cost,
                            event.instance_id,
                            event.request_id,
                            created_at_ms,
                        ),
                    )
                    before = self._snapshot_in_connection(connection, event.app_id)
                    next_total = before.total_cost + event.cost
                    threshold_exceeded = bool(
                        before.threshold is not None and next_total >= before.threshold
                    )
                    connection.execute(
                        """
                        UPDATE cust.applications
                        SET total_cost = ?, threshold_exceeded = ?
                        WHERE app_id = ?
                        """,
                        (next_total, int(threshold_exceeded), event.app_id),
                    )
                    after = self._snapshot_in_connection(connection, event.app_id)
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise

        notifications: List[Dict[str, Any]] = []
        if not before.threshold_exceeded and after.threshold_exceeded:
            notifications.append(
                {
                    "type": "threshold_exceeded",
                    **after.to_dict(),
                    "message": "Der konfigurierte Kostenschwellwert wurde überschritten.",
                }
            )
        return {"snapshot": after.to_dict(), "notifications": notifications}

    async def set_threshold(self, app_id: str, threshold: int) -> Dict[str, Any]:
        async with self._lock:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO cust.applications (app_id, total_cost, threshold, threshold_exceeded)
                    VALUES (?, 0, ?, 0)
                    ON CONFLICT(app_id) DO NOTHING
                    """,
                    (app_id, threshold),
                )
                current = self._snapshot_in_connection(connection, app_id)
                exceeded = current.total_cost >= threshold
                connection.execute(
                    """
                    UPDATE cust.applications
                    SET threshold = ?, threshold_exceeded = ?
                    WHERE app_id = ?
                    """,
                    (threshold, int(exceeded), app_id),
                )
                snapshot = self._snapshot_in_connection(connection, app_id)
        return snapshot.to_dict()

    async def snapshot(self, app_id: str) -> Dict[str, Any]:
        async with self._lock:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO cust.applications (app_id, total_cost, threshold, threshold_exceeded)
                    VALUES (?, 0, NULL, 0)
                    ON CONFLICT(app_id) DO NOTHING
                    """,
                    (app_id,),
                )
                return self._snapshot_in_connection(connection, app_id).to_dict()

    async def recent_operations(self, limit: int = 50) -> List[Dict[str, Any]]:
        async with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT app_id, operation, cost, instance_id, request_id, created_at_ms
                    FROM ops.operation_log
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [dict(row) for row in rows]

    def _snapshot_in_connection(self, connection: sqlite3.Connection, app_id: str) -> AppSnapshot:
        row = connection.execute(
            """
            SELECT app_id, total_cost, threshold, threshold_exceeded
            FROM cust.applications
            WHERE app_id = ?
            """,
            (app_id,),
        ).fetchone()
        if row is None:
            raise KeyError(app_id)
        return AppSnapshot(
            app_id=str(row["app_id"]),
            total_cost=int(row["total_cost"]),
            threshold=None if row["threshold"] is None else int(row["threshold"]),
            threshold_exceeded=bool(row["threshold_exceeded"]),
        )


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def add(self, app_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[app_id] = websocket

    async def remove(self, app_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if self._connections.get(app_id) is websocket:
                self._connections.pop(app_id, None)

    async def publish(self, app_id: str, payload: Dict[str, Any]) -> None:
        async with self._lock:
            websocket = self._connections.get(app_id)
        if websocket is None:
            return
        try:
            await websocket.send_json(payload)
        except Exception:
            await self.remove(app_id, websocket)


def create_app(store: DataManagerStore, manager: Optional[ConnectionManager] = None) -> FastAPI:
    connection_manager = manager or ConnectionManager()
    app = FastAPI(
        title="Math Factory Data Manager",
        version="1.0.0",
        description="REST and WebSocket API for application costs and threshold notifications.",
    )

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/apps/{app_id}/costs")
    async def costs(app_id: str) -> Dict[str, Any]:
        return await store.snapshot(app_id)

    @app.put("/apps/{app_id}/threshold")
    @app.patch("/apps/{app_id}/threshold")
    async def set_threshold(app_id: str, request: ThresholdRequest) -> Dict[str, Any]:
        snapshot = await store.set_threshold(app_id, request.threshold)
        await connection_manager.publish(app_id, {"type": "threshold_updated", **snapshot})
        return snapshot

    @app.get("/operations")
    async def recent_operations(limit: int = 50) -> Dict[str, Any]:
        if limit < 1 or limit > 500:
            raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
        return {"operations": await store.recent_operations(limit)}

    @app.post("/events/operation")
    async def operation_event(event: OperationEvent) -> Dict[str, Any]:
        result = await store.record_operation(event)
        for notification in result["notifications"]:
            await connection_manager.publish(event.app_id, notification)
        return result

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        app_id: Optional[str] = None
        try:
            while True:
                message = await websocket.receive_json()
                action = message.get("action")
                next_app_id = message.get("app_id", message.get("session_id"))
                if action not in {"register", "set_threshold", "ping"}:
                    await websocket.send_json({"type": "error", "message": "Unknown WebSocket action."})
                    continue
                if action == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue
                if not isinstance(next_app_id, str) or not next_app_id.strip():
                    await websocket.send_json({"type": "error", "message": "app_id must be a non-empty string."})
                    continue
                if app_id and app_id != next_app_id:
                    await connection_manager.remove(app_id, websocket)
                app_id = next_app_id
                await connection_manager.add(app_id, websocket)
                if "threshold" in message:
                    snapshot = await store.set_threshold(app_id, int(message["threshold"]))
                    await websocket.send_json({"type": "threshold_updated", **snapshot})
                else:
                    snapshot = await store.snapshot(app_id)
                if action == "register":
                    await websocket.send_json({"type": "registered", **snapshot})
        except WebSocketDisconnect:
            pass
        finally:
            if app_id:
                await connection_manager.remove(app_id, websocket)

    return app


def build_store_from_env() -> DataManagerStore:
    data_dir = os.getenv("DATA_DIR", "/data")
    return DataManagerStore(
        ops_db_path=os.getenv("OPS_DB_PATH", os.path.join(data_dir, "ops.sqlite3")),
        cust_db_path=os.getenv("CUST_DB_PATH", os.path.join(data_dir, "cust.sqlite3")),
    )


def main() -> None:
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("DATA_MANAGER_PORT", "8080"))
    uvicorn.run(create_app(build_store_from_env()), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
