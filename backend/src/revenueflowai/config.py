"""Application configuration, sourced from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development")
    demo_mode: bool = Field(default=True)

    database_url: str = Field(default="postgresql+asyncpg://revenueflow:revenueflow@localhost:5433/revenueflow")

    oidc_issuer: str = Field(default="http://localhost:8080/realms/revenueflow")
    oidc_audience: str = Field(default="revenueflow-backend")
    oidc_jwks_url: str = Field(
        default="http://localhost:8080/realms/revenueflow/protocol/openid-connect/certs"
    )
    jwt_leeway_seconds: int = Field(default=10)

    s3_endpoint_url: str = Field(default="http://localhost:4566")
    s3_access_key: str = Field(default="test")
    s3_secret_key: str = Field(default="test")
    s3_bucket_raw_imports: str = Field(default="raw-imports")
    s3_bucket_exports: str = Field(default="exports")
    s3_bucket_documents: str = Field(default="documents")
    s3_region: str = Field(default="us-east-1")

    anthropic_api_key: str | None = Field(default=None)
    live_planner_provider: str = Field(default="anthropic")  # "anthropic" | "bedrock"
    aws_region: str = Field(default="us-east-1")

    max_upload_bytes: int = Field(default=200 * 1024 * 1024)

    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
