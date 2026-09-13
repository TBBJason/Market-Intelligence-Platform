"""Environment-backed application configuration."""

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime configuration; secrets are never stored in source."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MI_",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+psycopg://market_intelligence:market_intelligence@localhost:5432/"
        "market_intelligence"
    )
    github_api_url: str = "https://api.github.com"
    github_token: SecretStr | None = None
    github_token_host: str = "api.github.com"
    github_token_port: int = Field(default=443, ge=1, le=65_535)
    http_user_agent: str = "ai-infrastructure-market-intelligence/0.1"
    http_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    http_max_attempts: int = Field(default=3, ge=1, le=5)
    http_max_retry_after_seconds: int = Field(default=60, ge=0, le=300)
    http_max_response_bytes: int = Field(default=2_000_000, ge=1_024, le=10_000_000)

    @field_validator("github_api_url")
    @classmethod
    def validate_github_api_url(cls, value: str) -> str:
        """Require a credential-safe HTTPS origin without userinfo, query, or fragment."""

        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("github_api_url must be a clean HTTPS URL")
        return value.rstrip("/")

    @field_validator("github_token_host")
    @classmethod
    def validate_token_host(cls, value: str) -> str:
        if not value or "/" in value or ":" in value:
            raise ValueError("github_token_host must be a hostname")
        return value.lower()


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings object per process."""

    return Settings()
