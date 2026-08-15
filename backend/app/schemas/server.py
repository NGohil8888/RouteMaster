from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List
from datetime import datetime


class OllamaServerBase(BaseModel):
    """Base schema for Ollama server."""
    
    name: str = Field(..., min_length=1, max_length=255)
    base_url: str = Field(..., description="Base URL of Ollama server")
    description: Optional[str] = None
    priority: int = Field(default=10, ge=1, le=100)
    weight: float = Field(default=1.0, ge=0.1)
    max_concurrent_requests: int = Field(default=100, ge=1)


class OllamaServerCreate(OllamaServerBase):
    """Schema for creating a server."""
    pass


class OllamaServerUpdate(BaseModel):
    """Schema for updating a server."""
    
    name: Optional[str] = None
    description: Optional[str] = None
    is_enabled: Optional[bool] = None
    priority: Optional[int] = None
    weight: Optional[float] = None
    max_concurrent_requests: Optional[int] = None


class OllamaServerResponse(OllamaServerBase):
    """Schema for server response."""
    
    id: int
    is_enabled: bool
    is_healthy: bool
    average_latency_ms: float
    error_rate: float
    current_active_requests: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_tokens_processed: int
    available_models: List[str]
    last_health_check: Optional[datetime]
    
    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    """Schema for creating a user."""
    
    username: str = Field(..., min_length=3, max_length=255)
    email: str = Field(..., description="User email")
    password: str = Field(..., min_length=8)
    is_admin: bool = False


class UserResponse(BaseModel):
    """Schema for user response."""
    
    id: int
    username: str
    email: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class Token(BaseModel):
    """Schema for authentication token."""
    
    access_token: str
    token_type: str = "bearer"


class ChatCompletionRequest(BaseModel):
    """Schema for chat completion request (OpenAI compatible)."""
    
    model: str
    messages: List[dict]
    stream: bool = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    num_predict: Optional[int] = None
    max_tokens: Optional[int] = None


class ChatCompletionResponse(BaseModel):
    """Schema for chat completion response."""
    
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[dict]
    usage: dict


class RequestLogResponse(BaseModel):
    """Schema for request log."""
    
    id: int
    model: str
    server_id: int
    status_code: int
    latency_ms: float
    tokens_input: int
    tokens_output: int
    error_message: Optional[str]
    retry_count: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class ServerStats(BaseModel):
    """Schema for server statistics."""
    
    server_id: int
    server_name: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    average_latency_ms: float
    error_rate: float
    total_tokens_processed: int
    current_active_requests: int
    is_healthy: bool


class ClusterStats(BaseModel):
    """Schema for cluster statistics."""
    
    total_servers: int
    healthy_servers: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    overall_success_rate: float
    total_active_requests: int
    total_tokens_processed: int
    servers: List[ServerStats]
