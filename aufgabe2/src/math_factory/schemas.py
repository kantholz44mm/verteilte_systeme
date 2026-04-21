from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class OperationResponse(BaseModel):
    name: str
    description: str
    expression: str
    cost: int = Field(ge=0)
    enabled: bool


class OperationListResponse(BaseModel):
    operations: List[OperationResponse]


class OperationUpdateRequest(BaseModel):
    cost: Optional[int] = Field(default=None, ge=0)
    enabled: Optional[bool] = None

