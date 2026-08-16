"""Configuration management for the Ollama Cloud API Gateway."""

import os
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Gateway settings loaded from environment variables."""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Ollama Cloud
    ollama_api_keys: str = ""
    ollama_base_url: str = "https://ollama.com"

    # Gateway behavior
    max_retries: int = 3
    request_timeout_seconds: float = 120.0
    health_check_interval_seconds: float = 30.0
    account_cooldown_seconds: float = 60.0

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @property
    def api_keys_list(self) -> List[str]:
        """Parse comma-separated API keys into a list."""
        if not self.ollama_api_keys:
            return []
        return [key.strip() for key in self.ollama_api_keys.split(",") if key.strip()]

    @property
    def ollama_api_base(self) -> str:
        """Return the OpenAI-compatible API base URL."""
        base = self.ollama_base_url.rstrip("/")
        return f"{base}/v1"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()