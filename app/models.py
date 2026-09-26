from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# =============================================================================
# 1. Health Response (GET /v1/healthz)
# =============================================================================

class HealthResponse(BaseModel):
    """
    Example:
    {
      "status": "ok",
      "uptime_seconds": 3600,
      "contexts_loaded": {
        "category": 5,
        "merchant": 50,
        "customer": 200,
        "trigger": 100
      }
    }
    """
    status: str = Field(default="ok", description="Liveness status")
    uptime_seconds: int = Field(default=0, description="Uptime in seconds since process start")
    contexts_loaded: Dict[str, int] = Field(
        default_factory=lambda: {"category": 0, "merchant": 0, "customer": 0, "trigger": 0},
        description="Count of contexts loaded per scope",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "ok",
                "uptime_seconds": 3600,
                "contexts_loaded": {
                    "category": 5,
                    "merchant": 50,
                    "customer": 200,
                    "trigger": 100,
                },
            }
        }
    }


# =============================================================================
# 2. Metadata Response (GET /v1/metadata)
# =============================================================================

class MetadataResponse(BaseModel):
    """
    Example:
    {
      "team_name": "Team Alpha",
      "team_members": ["Alice", "Bob"],
      "model": "claude-opus-4-7",
      "approach": "single-prompt composer with retrieval over digest items",
      "contact_email": "team@example.com",
      "version": "1.2.0",
      "submitted_at": "2026-04-26T08:00:00Z"
    }
    """
    team_name: str
    team_members: List[str]
    model: str
    approach: str
    version: str
    contact_email: Optional[str] = "team@example.com"
    submitted_at: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "team_name": "Team Alpha",
                "team_members": ["Alice", "Bob"],
                "model": "claude-opus-4-7",
                "approach": "single-prompt composer with retrieval over digest items",
                "contact_email": "team@example.com",
                "version": "1.2.0",
                "submitted_at": "2026-04-26T08:00:00Z",
            }
        }
    }


# =============================================================================
# 3. Context Push Request & Response (POST /v1/context)
# =============================================================================

class ContextPush(BaseModel):
    """
    Example:
    {
      "scope": "category",
      "context_id": "dentists",
      "version": 3,
      "payload": { ... },
      "delivered_at": "2026-04-26T10:00:00Z"
    }
    """
    scope: str
    context_id: str
    version: int
    payload: Dict[str, Any]
    delivered_at: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "scope": "category",
                "context_id": "dentists",
                "version": 3,
                "payload": {},
                "delivered_at": "2026-04-26T10:00:00Z",
            }
        }
    }


ContextPushRequest = ContextPush


class ContextPushResponse(BaseModel):
    """
    Examples:
    200: { "accepted": true, "ack_id": "ack_abc123", "stored_at": "2026-04-26T10:00:00.123Z" }
    409: { "accepted": false, "reason": "stale_version", "current_version": 5 }
    400: { "accepted": false, "reason": "invalid_scope", "details": "..." }
    """
    accepted: bool
    ack_id: Optional[str] = None
    stored_at: Optional[str] = None
    reason: Optional[str] = None
    current_version: Optional[int] = None
    details: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "accepted": True,
                "ack_id": "ack_abc123",
                "stored_at": "2026-04-26T10:00:00.123Z",
            }
        }
    }


# =============================================================================
# 4. Tick Request & Response (POST /v1/tick)
# =============================================================================

class TickRequest(BaseModel):
    """
    Example:
    {
      "now": "2026-04-26T10:30:00Z",
      "available_triggers": ["trg_2026_04_26_research_digest", "trg_2026_04_26_recall_priya"]
    }
    """
    now: str
    available_triggers: List[str] = Field(default_factory=list)

    model_config = {
        "json_schema_extra": {
            "example": {
                "now": "2026-04-26T10:30:00Z",
                "available_triggers": [
                    "trg_2026_04_26_research_digest",
                    "trg_2026_04_26_recall_priya",
                ],
            }
        }
    }


class TickAction(BaseModel):
    """
    Example action element in TickResponse.actions list:
    {
      "conversation_id": "conv_001",
      "merchant_id": "m_001_drmeera",
      "customer_id": null,
      "send_as": "vera",
      "trigger_id": "trg_2026_04_26_research_digest",
      "template_name": "vera_research_digest_v1",
      "template_params": ["Dr. Meera", "JIDA Oct issue", "..."],
      "body": "Dr. Meera, JIDA's Oct issue landed...",
      "cta": "open_ended",
      "suppression_key": "research:dentists:2026-W17",
      "rationale": "External research digest with merchant-relevant clinical anchor..."
    }
    """
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    send_as: Literal["vera", "merchant_on_behalf"] = "vera"
    trigger_id: str
    template_name: Optional[str] = None
    template_params: Optional[List[str]] = None
    body: str
    cta: str = "open_ended"
    suppression_key: str
    rationale: str


class TickResponse(BaseModel):
    """
    Example:
    {
      "actions": [
        {
          "conversation_id": "conv_001",
          "merchant_id": "m_001_drmeera",
          "customer_id": null,
          "send_as": "vera",
          "trigger_id": "trg_2026_04_26_research_digest",
          "template_name": "vera_research_digest_v1",
          "template_params": ["Dr. Meera", "JIDA Oct issue", "..."],
          "body": "Dr. Meera, JIDA's Oct issue landed...",
          "cta": "open_ended",
          "suppression_key": "research:dentists:2026-W17",
          "rationale": "External research digest with merchant-relevant clinical anchor..."
        }
      ]
    }
    """
    actions: List[TickAction] = Field(default_factory=list)

    model_config = {
        "json_schema_extra": {
            "example": {
                "actions": [
                    {
                        "conversation_id": "conv_001",
                        "merchant_id": "m_001_drmeera",
                        "customer_id": None,
                        "send_as": "vera",
                        "trigger_id": "trg_2026_04_26_research_digest",
                        "template_name": "vera_research_digest_v1",
                        "template_params": ["Dr. Meera", "JIDA Oct issue"],
                        "body": "Dr. Meera, JIDA's Oct issue landed...",
                        "cta": "open_ended",
                        "suppression_key": "research:dentists:2026-W17",
                        "rationale": "External research digest with merchant-relevant clinical anchor; merchant is a dentist with high-risk-adult patient cohort",
                    }
                ]
            }
        }
    }


# =============================================================================
# 5. Reply Request & Response (POST /v1/reply)
# =============================================================================

class ReplyRequest(BaseModel):
    """
    Example:
    {
      "conversation_id": "conv_001",
      "merchant_id": "m_001_drmeera",
      "customer_id": null,
      "from_role": "merchant",
      "message": "Yes, send me the abstract",
      "received_at": "2026-04-26T10:45:00Z",
      "turn_number": 2
    }
    """
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str
    message: str
    received_at: str
    turn_number: int

    model_config = {
        "json_schema_extra": {
            "example": {
                "conversation_id": "conv_001",
                "merchant_id": "m_001_drmeera",
                "customer_id": None,
                "from_role": "merchant",
                "message": "Yes, send me the abstract",
                "received_at": "2026-04-26T10:45:00Z",
                "turn_number": 2,
            }
        }
    }


class ReplyResponse(BaseModel):
    """
    Examples:
    send:
      {
        "action": "send",
        "body": "Sending now — also drafted a 90-sec patient-ed WhatsApp...",
        "cta": "open_ended",
        "rationale": "Honoring the merchant's accept; adding the next-best-step (patient-ed) as low-friction follow-on"
      }
    wait:
      {
        "action": "wait",
        "wait_seconds": 1800,
        "rationale": "Merchant asked for time; back off 30 min"
      }
    end:
      {
        "action": "end",
        "rationale": "Merchant said not interested; gracefully exiting conversation"
      }
    """
    action: Literal["send", "wait", "end"]
    body: Optional[str] = None
    cta: Optional[str] = None
    wait_seconds: Optional[int] = None
    rationale: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "action": "send",
                "body": "Sending now — also drafted a 90-sec patient-ed WhatsApp...",
                "cta": "open_ended",
                "rationale": "Honoring the merchant's accept; adding the next-best-step (patient-ed) as low-friction follow-on",
            }
        }
    }
