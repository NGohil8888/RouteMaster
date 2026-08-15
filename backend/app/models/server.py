from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime
import json


class OllamaServer(Base):
    """Database model for Ollama server."""
    
    __tablename__ = "ollama_servers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True, nullable=False)
    base_url = Column(String(500), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    
    # Connection settings
    api_key = Column(String(500), nullable=True)  # Encrypted if needed
    is_enabled = Column(Boolean, default=True, index=True)
    
    # Health and status
    is_healthy = Column(Boolean, default=True, index=True)
    consecutive_failures = Column(Integer, default=0)
    last_health_check = Column(DateTime, nullable=True)
    
    # Performance metrics
    average_latency_ms = Column(Float, default=0.0)
    error_rate = Column(Float, default=0.0)
    current_active_requests = Column(Integer, default=0)
    
    # Statistics
    total_requests = Column(Integer, default=0)
    successful_requests = Column(Integer, default=0)
    failed_requests = Column(Integer, default=0)
    total_tokens_processed = Column(Integer, default=0)
    
    # Model availability (JSON list)
    available_models = Column(Text, default="[]")
    
    # Load balancing configuration
    priority = Column(Integer, default=10)  # Lower = higher priority
    weight = Column(Float, default=1.0)  # For weighted load balancing
    max_concurrent_requests = Column(Integer, default=100)
    
    # Metadata
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "base_url": self.base_url,
            "description": self.description,
            "is_enabled": self.is_enabled,
            "is_healthy": self.is_healthy,
            "average_latency_ms": self.average_latency_ms,
            "error_rate": self.error_rate,
            "current_active_requests": self.current_active_requests,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "total_tokens_processed": self.total_tokens_processed,
            "available_models": json.loads(self.available_models or "[]"),
            "priority": self.priority,
            "weight": self.weight,
            "max_concurrent_requests": self.max_concurrent_requests,
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None,
        }


class User(Base):
    """Database model for user accounts."""
    
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(500), nullable=False)
    
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class RequestLog(Base):
    """Database model for request logging."""
    
    __tablename__ = "request_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Request details
    model = Column(String(255), index=True)
    server_id = Column(Integer, nullable=False)
    status_code = Column(Integer, index=True)
    
    # Performance
    latency_ms = Column(Float)
    tokens_input = Column(Integer, default=0)
    tokens_output = Column(Integer, default=0)
    
    # Error tracking
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    
    # Metadata
    created_at = Column(DateTime, server_default=func.now(), index=True)


class ModelAvailability(Base):
    """Track which models are available on which servers."""
    
    __tablename__ = "model_availability"
    
    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String(255), index=True, nullable=False)
    server_id = Column(Integer, nullable=False)
    
    is_available = Column(Boolean, default=True)
    last_checked = Column(DateTime, server_default=func.now())
    
    created_at = Column(DateTime, server_default=func.now())
