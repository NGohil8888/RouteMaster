"""FastAPI application with OpenAI-compatible endpoints."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app import dashboard_api, key_store, runtime_config
from app.account_manager import get_account_pool, initialize_pool_from_records
from app.health import health_monitor_loop
from app.logging_config import setup_logging
from app.proxy import proxy_request

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    setup_logging(settings.log_level)
    logger.info("Starting Ollama Cloud API Gateway v1.0.0")

    await runtime_config.load_overrides_into_settings()

    records = await key_store.load_keys()
    if not records:
        logger.warning(
            "No Ollama API keys configured yet. Add one from the dashboard at /dashboard, "
            "or set OLLAMA_API_KEYS in .env."
        )
    initialize_pool_from_records(records)

    health_task = asyncio.create_task(health_monitor_loop())

    yield

    logger.info("Shutting down Ollama Cloud API Gateway")
    health_task.cancel()
    try:
        await health_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Ollama Cloud API Failover Gateway",
    description="OpenAI-compatible API gateway with automatic failover across multiple Ollama Cloud accounts",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(dashboard_api.router)


@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    account_pool = get_account_pool()
    if account_pool is None:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "detail": "Account pool not initialized"},
        )

    return {
        "status": "healthy",
        "version": "1.0.0",
        "uptime_seconds": round(account_pool.uptime_seconds, 2),
        "accounts": {
            "total": account_pool.total_accounts,
            "healthy": account_pool.healthy_accounts,
            "available": account_pool.available_accounts,
        },
    }


@app.get("/status")
async def gateway_status():
    """Detailed gateway status endpoint (safe, no secrets)."""
    account_pool = get_account_pool()
    if account_pool is None:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "detail": "Account pool not initialized"},
        )

    return {
        "status": "healthy" if account_pool.available_accounts > 0 else "degraded",
        "version": "1.0.0",
        "uptime_seconds": round(account_pool.uptime_seconds, 2),
        "requests": {
            "total": account_pool.total_requests,
            "successful": account_pool.successful_requests,
            "failed": account_pool.failed_requests,
        },
        "accounts": account_pool.get_safe_statuses(),
    }


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"])
async def proxy_v1(request: Request, path: str):
    """Proxy all /v1/* requests to Ollama Cloud with failover."""
    method = request.method
    body = await request.body()
    query_string = str(request.query_params)

    headers_to_forward = {}
    for header in ["content-type", "accept", "user-agent", "x-request-id"]:
        value = request.headers.get(header)
        if value:
            headers_to_forward[header] = value

    response = await proxy_request(
        method=method,
        path=f"v1/{path}",
        request_headers=headers_to_forward,
        body=body if body else None,
        query_string=query_string,
    )

    return response


@app.get("/")
async def root():
    """Root endpoint with basic info."""
    return {
        "name": "Ollama Cloud API Failover Gateway",
        "version": "1.0.0",
        "docs": "/docs",
        "dashboard": "/dashboard",
        "health": "/health",
        "status": "/status",
        "openai_compatible": "/v1",
    }


if STATIC_DIR.is_dir():
    app.mount("/dashboard", StaticFiles(directory=str(STATIC_DIR), html=True), name="dashboard")