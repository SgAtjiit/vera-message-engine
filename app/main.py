from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict

from pathlib import Path
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from app.endpoints import context, health, metadata, reply, tick
from app.state import state

# =============================================================================
# Logging Configuration
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("vera.main")

# =============================================================================
# Application Lifespan (Startup & Shutdown)
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle:
    - On startup: Load full expanded/*.json dataset into VeraState.
    - Log loaded context counts and system readiness.
    """
    logger.info("Initializing vera-bot service...")
    loaded_count = state.load_expanded_dataset()
    counts = state.get_context_counts()
    logger.info(
        "Startup context ingestion complete: %d contexts loaded (category=%d, merchant=%d, customer=%d, trigger=%d)",
        loaded_count,
        counts["category"],
        counts["merchant"],
        counts["customer"],
        counts["trigger"],
    )
    yield
    logger.info("vera-bot service shutting down...")


# =============================================================================
# FastAPI Application Creation
# =============================================================================

app = FastAPI(
    title="vera-bot",
    description="Merchant AI Assistant for magicpin WhatsApp engagement",
    version="1.0.0",
    lifespan=lifespan,
)

# =============================================================================
# Timeout & Request Logging Middleware (< 25s Safety Guard)
# =============================================================================

@app.middleware("http")
async def timeout_and_logging_middleware(request: Request, call_next):
    """
    Enforces a strict 25.0-second safety timeout on every request
    (guaranteeing the server never exceeds the 30-second judge harness limit),
    logs request arrival, completion status, and execution duration.
    """
    start_time = time.time()
    method = request.method
    path = request.url.path

    logger.info("--> %s %s", method, path)

    try:
        # Enforce 25-second processing budget
        response = await asyncio.wait_for(call_next(request), timeout=25.0)
        duration_ms = (time.time() - start_time) * 1000
        logger.info("<-- %s %s [%d] (%.1fms)", method, path, response.status_code, duration_ms)
        return response

    except asyncio.TimeoutError:
        duration_ms = (time.time() - start_time) * 1000
        logger.error("Request %s %s timed out after %.1fms (exceeded 25.0s budget)", method, path, duration_ms)

        # Return safe domain-specific JSON depending on endpoint
        if path == "/v1/tick":
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "actions": [],
                    "timeout": True,
                    "rationale": "Execution budget (25s) reached; safely returned empty actions without blocking",
                },
            )
        elif path == "/v1/reply":
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "action": "wait",
                    "wait_seconds": 60,
                    "rationale": "Execution budget (25s) reached; safely backed off to maintain responsiveness",
                },
            )

        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={
                "error": "timeout",
                "message": "Request processing exceeded safety budget of 25.0 seconds",
            },
        )

    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000
        logger.exception("Unhandled error processing %s %s after %.1fms: %s", method, path, duration_ms, exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_server_error",
                "message": "An unexpected error occurred while processing the request",
                "details": str(exc),
            },
        )


# =============================================================================
# Global Exception Handlers
# =============================================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return structured JSON on invalid request schemas."""
    logger.warning("Validation error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "accepted": False,
            "error": "validation_error",
            "details": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch any unhandled exceptions and return safe JSON instead of crashing."""
    logger.exception("Global exception handler caught: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_error",
            "message": "Service encountered an error",
            "details": str(exc),
        },
    )


# =============================================================================
# Router Mounts
# =============================================================================

app.include_router(health.router)
app.include_router(metadata.router)
app.include_router(context.router)
app.include_router(tick.router)
app.include_router(reply.router)


@app.get("/")
async def root():
    return {
        "name": "vera-bot",
        "status": "running",
        "version": "1.0.0",
        "contexts_loaded": state.get_context_counts(),
    }
