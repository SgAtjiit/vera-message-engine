from __future__ import annotations

from fastapi import APIRouter
from app.models import HealthResponse
from app.state import state

router = APIRouter()


@router.get("/v1/health", response_model=HealthResponse)
@router.get("/v1/healthz", response_model=HealthResponse)
@router.get("/health", response_model=HealthResponse)
@router.get("/healthz", response_model=HealthResponse)
async def health():
    """
    Lightweight liveness probe returning status, uptime in seconds,
    and precomputed count of loaded contexts per scope in O(1) time.
    Zero disk/DB checks — returns immediate 200 OK for external pingers.
    """
    return HealthResponse(
        status="ok",
        uptime_seconds=state.get_uptime_seconds(),
        contexts_loaded=state.get_context_counts(),
    )
