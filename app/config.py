"""Configuration management for the Ollama Cloud API Gateway."""

import os
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server settings
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    # Ollama Cloud settings
    ollama_api_keys: str = Field(default="", alias="OLLAMA_API_KEYS")
    ollama_base_url: str = Field(default="https://ollama.com", alias="OLLAMA_BASE_URL")

    # Retry and failover settings
    max_retries: int = Field(default=3, alias="MAX_RETRIES")
    request_timeout_seconds: float = Field(default=120.0, alias="REQUEST_TIMEOUT_SECONDS")
    account_cooldown_seconds: float = Field(default=60.0, alias="ACCOUNT_COOLDOWN_SECONDS")
    health_check_interval_seconds: float = Field(default=30.0, alias="HEALTH_CHECK_INTERVAL_SECONDS")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Health check settings
    health_check_timeout_seconds: float = Field(default=15.0, alias="HEALTH_CHECK_TIMEOUT_SECONDS")
    health_check_model: str = Field(default="gemma3:4b", alias="HEALTH_CHECK_MODEL")

    # Request settings
    stream_timeout_seconds: float = Field(default=300.0, alias="STREAM_TIMEOUT_SECONDS")
    max_concurrent_requests_per_account: int = Field(default=10, alias="MAX_CONCURRENT_REQUESTS_PER_ACCOUNT")

    # Optional admin token for the dashboard API. When unset (the default),
    # /api/* stays open as before - matches the single-user local-tool mode
    # the project has shipped with. Setting GATEWAY_ADMIN_TOKEN locks every
    # /api/* endpoint behind Bearer auth.
    gateway_admin_token: Optional[str] = Field(default=None, alias="GATEWAY_ADMIN_TOKEN")

    @property
    def api_keys_list(self) -> List[str]:
        """Return the list of API keys."""
        return [key.strip() for key in self.ollama_api_keys.split(",") if key.strip()]

    @property
    def ollama_api_base(self) -> str:
        """Return the base URL for Ollama Cloud API."""
        base = self.ollama_base_url.rstrip("/")
        return base

    @property
    def ollama_openai_base(self) -> str:
        """Return the OpenAI-compatible base URL."""
        return f"{self.ollama_api_base}/v1"


# Global settings instance
settings = Settings()