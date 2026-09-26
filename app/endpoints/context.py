from __future__ import annotations

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Response, status
from app.models import ContextPush, ContextPushResponse
from app.state import state

router = APIRouter()

VALID_SCOPES = {"category", "merchant", "customer", "trigger"}


@router.post("/v1/context", response_model=ContextPushResponse)
async def push_context(body: ContextPush, response: Response):
    """
    Ingest a context push across the 4-context layers.
    Idempotent by (context_id, version).
    Higher version replaces earlier version atomically.
    Lower version returns 409 Conflict.
    Invalid scope returns 400 Bad Request.
    """
    if body.scope not in VALID_SCOPES:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return ContextPushResponse(
            accepted=False,
            reason="invalid_scope",
            details=f"Invalid scope '{body.scope}'. Must be one of: {', '.join(sorted(VALID_SCOPES))}",
        )

    accepted, reason, current_version = state.upsert_context(
        scope=body.scope,
        context_id=body.context_id,
        version=body.version,
        payload=body.payload,
    )

    if not accepted:
        response.status_code = status.HTTP_409_CONFLICT
        return ContextPushResponse(
            accepted=False,
            reason=reason,
            current_version=current_version,
        )

    # UTC ISO timestamp (e.g. 2026-09-27T00:40:00.123Z)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    return ContextPushResponse(
        accepted=True,
        ack_id=str(uuid.uuid4()),
        stored_at=now_iso,
    )
