"""FastAPI routes for OpenAI-compatible proxy with automatic failover."""

import json
import logging
import time
from typing import AsyncGenerator, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.account_manager import Account, AccountManager
from app.config import Settings
from app.models import HealthResponse, StatusResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level references set during app startup
_account_manager: Optional[AccountManager] = None
_settings: Optional[Settings] = None


def configure_proxy(account_manager: AccountManager, settings: Settings) -> None:
    """Configure the proxy module with runtime dependencies."""
    global _account_manager, _settings
    _account_manager = account_manager
    _settings = settings


# OpenAI-compatible endpoints to proxy
OPENAI_ENDPOINTS = {
    "/v1/chat/completions",
    "/v1/completions",
    "/v1/models",
    "/v1/embeddings",
    "/v1/responses",
}


@router.api_route("/health", methods=["GET"])
async def health() -> JSONResponse:
    """Return gateway health and account summary."""
    if _account_manager is None:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    total = len(_account_manager.accounts)
    healthy = sum(
        1 for a in _account_manager.accounts if a.state.status.value == "healthy"
    )
    unavailable = total - healthy

    details = []
    for a in _account_manager.accounts:
        state = a.state.model_dump()
        state.pop("api_key", None)
        details.append(state)

    return JSONResponse(
        content=HealthResponse(
            status="healthy" if healthy > 0 else "degraded",
            accounts={"total": total, "healthy": healthy, "unavailable": unavailable},
            account_details=details,
            uptime_seconds=time.time() - getattr(health, "_start_time", time.time()),
        ).model_dump()
    )


health._start_time = time.time()


@router.api_route("/status", methods=["GET"])
async def status() -> JSONResponse:
    """Return high-level gateway status."""
    if _account_manager is None or _settings is None:
        raise HTTPException(status_code=503, detail="Gateway not initialized")

    total = len(_account_manager.accounts)
    healthy = sum(
        1 for a in _account_manager.accounts if a.state.status.value == "healthy"
    )

    return JSONResponse(
        content=StatusResponse(
            status="healthy" if healthy > 0 else "degraded",
            accounts_total=total,
            accounts_healthy=healthy,
            accounts_unavailable=total - healthy,
            upstream_url=_settings.ollama_api_base,
        ).model_dump()
    )


@router.api_route("/v1/models", methods=["GET"])
async def list_models(request: Request) -> JSONResponse:
    """Proxy models list with failover."""
    return await _proxy_request(request)


@router.api_route("/v1/models/{model_id:path}", methods=["GET"])
async def get_model(request: Request, model_id: str) -> JSONResponse:
    """Proxy single model retrieval with failover."""
    return await _proxy_request(request)


@router.api_route("/v1/chat/completions", methods=["POST"])
async def chat_completions(request: Request) -> StreamingResponse | JSONResponse:
    """Proxy chat completions with failover and streaming support."""
    return await _proxy_request(request)


@router.api_route("/v1/completions", methods=["POST"])
async def completions(request: Request) -> StreamingResponse | JSONResponse:
    """Proxy completions with failover and streaming support."""
    return await _proxy_request(request)


@router.api_route("/v1/embeddings", methods=["POST"])
async def embeddings(request: Request) -> JSONResponse:
    """Proxy embeddings with failover."""
    return await _proxy_request(request)


@router.api_route("/v1/responses", methods=["POST"])
async def responses(request: Request) -> StreamingResponse | JSONResponse:
    """Proxy responses API with failover and streaming support."""
    return await _proxy_request(request)


async def _proxy_request(request: Request) -> StreamingResponse | JSONResponse:
    """Proxy a request to an upstream Ollama account with automatic failover."""
    if _account_manager is None or _settings is