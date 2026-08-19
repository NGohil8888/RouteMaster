"""REST API backing the web dashboard: key management, live key testing,
usage stats, and runtime settings. Mounted under /api by main.py.
"""

import hmac
import logging
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security.utils import get_authorization_scheme_param
from pydantic import BaseModel, Field

from app import key_store, runtime_config
from app.account_manager import get_account_pool, initialize_pool_from_records
from app.config import settings
from app.utils import mask_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# --- auth gating ------------------------------------------------------------

def _extract_token(request: Request) -> Optional[str]:
    """Pull an admin token out of the request, if one is present.

    Supports two header shapes to stay friendly to both browsers (which can't
    set Authorization without a CORS preflight) and curl/script callers:
      - `Authorization: Bearer ***`
      - `X-Gateway-Token: ***`
    Returns None if no token was supplied. Caller decides whether absence
    is acceptable (i.e. no token configured) or a 401.
    """
    auth_header = request.headers.get("authorization") or ""
    scheme, token = get_authorization_scheme_param(auth_header)
    if scheme.lower() == "bearer" and token:
        return token.strip()
    custom = request.headers.get("x-gateway-token")
    if custom:
        return custom.strip()
    return None


async def require_admin(request: Request) -> None:
    """Dependency: 401 unless `settings.gateway_admin_token` matches the caller.

    When `GATEWAY_ADMIN_TOKEN` is unset (the default), no auth is required -
    keeps the single-user local-tool behavior unchanged. Anything else
    enforces a constant-time comparison to avoid timing leaks.
    """
    expected = getattr(settings, "gateway_admin_token", None)
    if not expected:
        return
    supplied = _extract_token(request)
    if supplied and hmac.compare_digest(supplied, expected):
        return
    # Avoid leaking whether the token was wrong-shape vs wrong-value:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Admin token required. Set the Authorization: Bearer header (or X-Gateway-Token).",
        headers={"WWW-Authenticate": "Bearer"},
    )


# --- body models ------------------------------------------------------------

class KeyIn(BaseModel):
    label: Optional[str] = None
    api_key: str


class KeyUpdateIn(BaseModel):
    label: Optional[str] = None
    api_key: Optional[str] = None


# Bounds for runtime-editable settings. These mirror what's safe for the
# proxy/health subsystems: e.g. max_retries=0 hangs the gateway forever,
# max_concurrent_requests_per_account=0 makes every request 503, and a
# negative timeout makes httpx raise immediately.
class SettingsIn(BaseModel):
    max_retries: Optional[int] = Field(default=None, ge=1, le=64)
    account_cooldown_seconds: Optional[float] = Field(default=None, ge=0.0, le=86400.0)
    health_check_interval_seconds: Optional[float] = Field(default=None, ge=1.0, le=3600.0)
    request_timeout_seconds: Optional[float] = Field(default=None, ge=1.0, le=3600.0)
    stream_timeout_seconds: Optional[float] = Field(default=None, ge=1.0, le=86400.0)
    max_concurrent_requests_per_account: Optional[int] = Field(default=None, ge=1, le=10000)
    # String-typed fields. `gateway_admin_token` accepts None (leave unchanged),
    # an empty string (explicit clear), or a string of length 8-256. The
    # 8-char minimum for a *non-empty* token is enforced in runtime_config,
    # not here - a Field(min_length=8) would reject the empty-string clear
    # signal with a 422 before the request body could ever reach that logic.
    gateway_admin_token: Optional[str] = Field(default=None, max_length=256)


async def _resync_pool():
    """Reconcile the live account pool with whatever is currently persisted."""
    records = await key_store.load_keys()
    pool = get_account_pool()
    if pool is None:
        initialize_pool_from_records(records)
    else:
        await pool.sync_from_records(records)
    return records


@router.get("/keys", dependencies=[Depends(require_admin)])
async def list_keys():
    records = await key_store.load_keys()
    pool = get_account_pool()
    statuses_by_id = {}
    if pool is not None:
        for s in pool.get_safe_statuses():
            if s.get("key_id"):
                statuses_by_id[s["key_id"]] = s

    return [
        {
            "id": r.id,
            "label": r.label,
            "key_preview": mask_key(r.api_key),
            "status": statuses_by_id.get(r.id),
        }
        for r in records
    ]


@router.post("/keys", status_code=201, dependencies=[Depends(require_admin)])
async def create_key(payload: KeyIn):
    if not payload.api_key or not payload.api_key.strip():
        raise HTTPException(status_code=400, detail="api_key is required")
    record = await key_store.add_key(payload.label or "", payload.api_key.strip())
    await _resync_pool()
    return {"id": record.id, "label": record.label, "key_preview": mask_key(record.api_key)}


@router.put("/keys/{key_id}", dependencies=[Depends(require_admin)])
async def edit_key(key_id: str, payload: KeyUpdateIn):
    record = await key_store.update_key(
        key_id,
        label=payload.label,
        api_key=payload.api_key.strip() if payload.api_key else None,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Key not found")
    await _resync_pool()
    return {"id": record.id, "label": record.label, "key_preview": mask_key(record.api_key)}


@router.delete("/keys/{key_id}", dependencies=[Depends(require_admin)])
async def remove_key(key_id: str):
    ok = await key_store.delete_key(key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found")
    await _resync_pool()
    return {"deleted": True}


@router.post("/keys/{key_id}/test", dependencies=[Depends(require_admin)])
async def test_key(key_id: str):
    """Actually hit Ollama Cloud with this specific key, independent of the pool's state."""
    records = await key_store.load_keys()
    record = next((r for r in records if r.id == key_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="Key not found")

    url = f"{settings.ollama_openai_base}/models"
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {record.api_key}"})
        latency_ms = round((time.time() - start) * 1000, 1)
        if resp.status_code == 200:
            return {"success": True, "status_code": 200, "latency_ms": latency_ms, "error": None}
        try:
            body = resp.json()
            err = body.get("error")
            msg = err.get("message") if isinstance(err, dict) else (err or f"HTTP {resp.status_code}")
        except Exception:
            msg = f"HTTP {resp.status_code}"
        return {"success": False, "status_code": resp.status_code, "latency_ms": latency_ms, "error": msg}
    except httpx.HTTPError as e:
        latency_ms = round((time.time() - start) * 1000, 1)
        return {"success": False, "status_code": None, "latency_ms": latency_ms, "error": str(e)}


@router.get("/usage", dependencies=[Depends(require_admin)])
async def usage():
    pool = get_account_pool()
    if pool is None:
        return {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "accounts": [],
        }
    statuses = pool.get_safe_statuses()
    return {
        "total_prompt_tokens": sum(s.get("total_prompt_tokens", 0) for s in statuses),
        "total_completion_tokens": sum(s.get("total_completion_tokens", 0) for s in statuses),
        "total_tokens": sum(s.get("total_tokens", 0) for s in statuses),
        "total_requests": pool.total_requests,
        "successful_requests": pool.successful_requests,
        "failed_requests": pool.failed_requests,
        "accounts": statuses,
    }


@router.get("/overview", dependencies=[Depends(require_admin)])
async def overview():
    pool = get_account_pool()
    if pool is None:
        return {
            "status": "not_initialized",
            "uptime_seconds": 0,
            "accounts": {"total": 0, "healthy": 0, "available": 0},
            "requests": {"total": 0, "successful": 0, "failed": 0},
        }
    return {
        "status": "healthy" if pool.available_accounts > 0 else "degraded",
        "uptime_seconds": round(pool.uptime_seconds, 2),
        "accounts": {
            "total": pool.total_accounts,
            "healthy": pool.healthy_accounts,
            "available": pool.available_accounts,
        },
        "requests": {
            "total": pool.total_requests,
            "successful": pool.successful_requests,
            "failed": pool.failed_requests,
        },
    }


@router.get("/settings", dependencies=[Depends(require_admin)])
async def get_settings_endpoint():
    return await runtime_config.get_editable_settings()


@router.put("/settings", dependencies=[Depends(require_admin)])
async def update_settings_endpoint(payload: SettingsIn):
    # SettingsIn already enforces Field(ge/le) bounds, so passing payload
    # straight through is safe - any value the dashboard can submit has
    # already been validated.
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        return await runtime_config.update_settings(updates)
    except runtime_config.SettingsValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/auth/status")
async def auth_status(request: Request) -> Dict[str, Any]:
    """Tell the dashboard whether /api/* is locked, and whether the caller's
    supplied token (if any) is valid. The token value is never returned -
    only a yes/no on the current request.
    """
    token = settings.gateway_admin_token
    required = bool(token)
    ok = False
    if required:
        supplied = _extract_token(request)
        if supplied and hmac.compare_digest(supplied, token):
            ok = True
    return {"required": required, "ok": ok}
