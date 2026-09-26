from __future__ import annotations

from fastapi import APIRouter
from app.models import MetadataResponse
from app.config import (
    TEAM_NAME,
    TEAM_MEMBERS,
    MODEL,
    APPROACH,
    VERSION,
    CONTACT_EMAIL,
    SUBMITTED_AT,
)

router = APIRouter()


@router.get("/v1/metadata", response_model=MetadataResponse)
async def metadata():
    """
    Return bot and team metadata loaded from config.py.
    """
    return MetadataResponse(
        team_name=TEAM_NAME,
        team_members=TEAM_MEMBERS,
        model=MODEL,
        approach=APPROACH,
        version=VERSION,
        contact_email=CONTACT_EMAIL,
        submitted_at=SUBMITTED_AT,
    )
