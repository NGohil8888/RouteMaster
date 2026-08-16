"""Pydantic models for the Ollama Cloud API Gateway."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AccountStatus(str, Enum):
    """Possible states for an Ollama Cloud API account."""

    HEALTHY = "healthy"
    RATE_LIMITED = "rate_limited"
    TOKEN_EXHAUSTED = "token_exhausted"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    AUTH_ERROR = "auth_error"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class AccountState(BaseModel):
    """Represents the current state of a single Ollama Cloud API account."""

    index: int
    api_key_preview: str
    status: AccountStatus = AccountStatus.UNKNOWN
    last_checked: Optional[datetime] = None
    last_error: Optional[str] = None
    last_status_code: Optional[int] = None
    cooldown_until: Optional[datetime] = None
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class HealthResponse(BaseModel):
    """Response model for the /health endpoint."""

    status: str
    accounts: Dict[str, int]
    account_details: list
    uptime_seconds: float


class StatusResponse(BaseModel):
    """Response model for the /status endpoint."""

    status: str
    version: str = "1.0.0"
    accounts_total: int
    accounts_healthy: int
    accounts_unavailable: int
    upstream_url: str


class ProxyErrorResponse(BaseModel):
    """OpenAI-compatible error response."""

    error: Dict[str, Any]