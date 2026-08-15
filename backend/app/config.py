from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings."""
    
    APP_NAME: str = "Hermes Ollama Gateway"
    APP_VERSION: str = "1.0.0"
    
    # Database
    DATABASE_URL: str = "sqlite:///./data/hermes.db"
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    
    # Health Monitoring
    HEALTH_CHECK_INTERVAL_SECONDS: int = 15
    HEALTH_CHECK_TIMEOUT_SECONDS: int = 10
    HEALTH_CHECK_FAILURES_THRESHOLD: int = 3
    
    # Request Configuration
    REQUEST_TIMEOUT_SECONDS: int = 120
    MAX_RETRIES: int = 3
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60
    
    # Logging
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    # Features
    ENABLE_METRICS: bool = True
    ENABLE_REQUEST_LOGGING: bool = True
    MAX_REQUEST_LOG_RETENTION_DAYS: int = 30
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
