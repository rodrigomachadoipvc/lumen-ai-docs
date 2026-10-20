"""Liveness endpoint used by Docker, load balancers and CI smoke tests."""

from importlib.metadata import version
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str


@router.get("/health")
async def health() -> HealthResponse:
    """Report that the API process is up."""
    return HealthResponse(status="ok", version=version("lumen"))
