from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ticket-classifier"
    environment: Literal["development", "staging", "production", "testing"] = "development"
    debug: bool = False

    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1

    api_prefix: str = "/api/v1"

    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    model_path: str = "models/distilbert"
    baseline_model_path: str = "models/baseline.joblib"
    model_device: Literal["cpu", "cuda", "mps"] = "cpu"
    max_batch_size: int = 32
    inference_timeout: float = 30.0

    # Model artifact download
    model_s3_bucket: str | None = None
    model_s3_key: str | None = None
    model_gcs_bucket: str | None = None
    model_gcs_path: str | None = None
    model_checksum: str | None = None  # SHA256
    model_download_timeout: float = 300.0

    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 10

    # Database
    database_url: str = "sqlite+aiosqlite:///./test.db"

    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100
    rate_limit_window: int = 60

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:8000"]
    )
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])

    # Auth / JWT
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    pii_redaction_enabled: bool = True
    pii_patterns: list[str] = Field(
        default_factory=lambda: [
            r"\b\d{3}-\d{2}-\d{4}\b",
            r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        ]
    )

    health_check_interval: int = 30
    health_check_timeout: float = 5.0

    @field_validator("model_path", "baseline_model_path", mode="before")
    @classmethod
    def resolve_paths(cls, v: str) -> str:
        if not Path(v).is_absolute():
            return str(Path.cwd() / v)
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"


@lru_cache
def get_settings() -> Settings:
    return Settings()
