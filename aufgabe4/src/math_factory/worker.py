from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response

from .operations import DEFAULT_OPERATION_DEFINITIONS
from .rpc import process_jsonrpc_bytes_with_notifications
from .schemas import OperationUpdateRequest
from .state import MathFactoryState


class AccountingMathFactoryState(MathFactoryState):
    def __init__(self, instance_id: str) -> None:
        super().__init__()
        self.instance_id = instance_id

    def execute_with_notifications(
        self,
        name: str,
        arguments: List[object],
        session_id: Optional[str] = None,
    ) -> Tuple[Any, List[Dict[str, object]]]:
        definition = DEFAULT_OPERATION_DEFINITIONS.get(name)
        if definition is None:
            raise KeyError(name)
        with self._lock:
            config = self._operations.get(name)
            if config is None:
                raise KeyError(name)
            if not config["enabled"]:
                raise RuntimeError(name)
            cost = int(config["cost"])
        result = definition["evaluator"](*arguments)
        notifications: List[Dict[str, object]] = []
        if session_id is not None:
            notifications.append(
                {
                    "type": "operation_charged",
                    "app_id": session_id,
                    "operation": name,
                    "cost": cost,
                    "instance_id": self.instance_id,
                    "result": result,
                }
            )
        return result, notifications


class DataManagerClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def publish_operation_events(self, notifications: List[Dict[str, Any]]) -> None:
        events = [notification for notification in notifications if notification.get("type") == "operation_charged"]
        if not events:
            return
        async with httpx.AsyncClient(timeout=3.0) as client:
            for event in events:
                try:
                    await client.post(f"{self.base_url}/events/operation", json=event)
                except Exception:
                    # JSON-RPC responses must not fail because accounting is temporarily unreachable.
                    continue


def _request_id_from_body(body: bytes) -> Optional[str]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict) and "id" in payload:
        return str(payload["id"])
    return None


def create_app(state: AccountingMathFactoryState, data_manager: DataManagerClient) -> FastAPI:
    app = FastAPI(
        title="Math Factory Worker",
        version="1.0.0",
        description="Scalable JSON-RPC worker instance.",
        docs_url=None,
        openapi_url=None,
    )

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok", "instance_id": state.instance_id}

    @app.get("/operations")
    async def list_operations() -> Dict[str, Any]:
        return {"operations": state.list_operations()}

    @app.get("/operations/{name}")
    async def get_operation(name: str) -> Dict[str, Any]:
        try:
            return state.get_operation(name)
        except KeyError:
            raise HTTPException(status_code=404, detail="Unknown operation.")

    @app.put("/operations/{name}")
    @app.patch("/operations/{name}")
    async def update_operation(
        name: str, update: OperationUpdateRequest
    ) -> Dict[str, Any]:
        try:
            return state.update_operation(
                name, **update.model_dump(exclude_none=True)
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Unknown operation.")
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))

    @app.post("/rpc")
    async def rpc_endpoint(request: Request) -> Response:
        body = await request.body()
        request_id = _request_id_from_body(body)
        response_body, notifications = process_jsonrpc_bytes_with_notifications(state, body)
        for notification in notifications:
            if notification.get("type") == "operation_charged":
                notification["request_id"] = request_id
        await data_manager.publish_operation_events(notifications)
        if response_body is None:
            return Response(status_code=204)
        return Response(content=response_body, media_type="application/json")

    return app


def main() -> None:
    instance_id = os.getenv("INSTANCE_ID", os.getenv("HOSTNAME", "mf-worker"))
    data_manager_url = os.getenv("DATA_MANAGER_URL", "http://data-manager:8080")
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("RPC_PORT", "8081"))
    app = create_app(AccountingMathFactoryState(instance_id), DataManagerClient(data_manager_url))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
