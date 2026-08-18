"""Data models for the Ollama Cloud API Gateway."""

from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class AccountState(str, Enum):
    """Possible states for an Ollama Cloud API account."""

    HEALTHY = "healthy"
    RATE_LIMITED = "rate_limited"
    TOKEN_EXHAUSTED = "token_exhausted"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    AUTH_ERROR = "auth_error"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class AccountStatus(BaseModel):
    """Status information for a single Ollama Cloud account."""

    index: int = Field(..., description="Account index in the pool")
    key_id: Optional[str] = None
    label: str = ""
    key_preview: Optional[str] = None
    state: AccountState = Field(default=AccountState.UNKNOWN)
    last_error: Optional[str] = None
    last_used: Optional[datetime] = None
    last_checked: Optional[datetime] = None
    failure_count: int = 0
    success_count: int = 0
    cooldown_until: Optional[datetime] = None
    rate_limit_reset: Optional[datetime] = None
    consecutive_failures: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat() if v else None}
    )


class GatewayStatus(BaseModel):
    """Overall gateway status response."""

    status: str = "healthy"
    version: str = "1.0.0"
    uptime_seconds: float = 0.0
    accounts: Dict[str, Any] = Field(default_factory=dict)
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0


class HealthCheckResult(BaseModel):
    """Result of a health check for a single account."""

    index: int
    healthy: bool
    state: AccountState
    response_time_ms: Optional[float] = None
    error: Optional[str] = None
    model_available: Optional[bool] = None


class ProxyRequest(BaseModel):
    """Internal proxy request tracking."""

    method: str
    path: str
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Optional[bytes] = None
    stream: bool = False


class ProxyResponse(BaseModel):
    """Internal proxy response tracking."""

    status_code: int
    headers: Dict[str, str] = Field(default_factory=dict)
    content: Optional[bytes] = None
    stream: bool = False