from __future__ import annotations

import asyncio
import os
from itertools import cycle
from typing import Dict, List

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response


class RoundRobinRouter:
    def __init__(self, worker_urls: List[str]) -> None:
        if not worker_urls:
            raise ValueError("At least one worker URL is required.")
        self._urls = [url.rstrip("/") for url in worker_urls]
        self._cycle = cycle(self._urls)
        self._lock = asyncio.Lock()

    async def next_url(self) -> str:
        async with self._lock:
            return next(self._cycle)

    def workers(self) -> List[str]:
        return list(self._urls)


def create_app(router: RoundRobinRouter) -> FastAPI:
    app = FastAPI(
        title="Math Factory JSON-RPC Gateway",
        version="1.0.0",
        description="Round-robin JSON-RPC gateway for Math Factory worker instances.",
        docs_url=None,
        openapi_url=None,
    )

    @app.get("/health")
    async def health() -> Dict[str, object]:
        return {"status": "ok", "workers": router.workers()}

    @app.post("/rpc")
    async def rpc_gateway(request: Request) -> Response:
        target = await router.next_url()
        body = await request.body()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                upstream = await client.post(
                    f"{target}/rpc",
                    content=body,
                    headers={"content-type": request.headers.get("content-type", "application/json")},
                )
        except httpx.HTTPError as error:
            raise HTTPException(status_code=502, detail=f"Worker {target} is unavailable.") from error
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "application/json"),
        )

    return app


def worker_urls_from_env() -> List[str]:
    raw_urls = os.getenv("WORKER_URLS", "http://math-factory-worker:8081")
    return [url.strip() for url in raw_urls.split(",") if url.strip()]


def main() -> None:
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("GATEWAY_PORT", "8081"))
    uvicorn.run(create_app(RoundRobinRouter(worker_urls_from_env())), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
