"""Application configuration."""
import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # Application
    app_name: str = Field(default="falcon-ml-inference-platform")
    app_version: str = Field(default="1.0.0")
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    worker_id: str = Field(default="worker-1")

    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    workers: int = Field(default=1)
    reload: bool = Field(default=False)

    # Model
    model_path: str = Field(default="/app/models/classifier.pkl")
    model_type: str = Field(default="sklearn")
    enable_batching: bool = Field(default=True)
    batch_size: int = Field(default=32)
    batch_timeout_ms: int = Field(default=100)

    # Redis
    redis_host: str = Field(default="redis")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=0)
    redis_password: Optional[str] = Field(default=None)
    redis_max_connections: int = Field(default=50)
    redis_socket_timeout: int = Field(default=5)
    redis_socket_connect_timeout: int = Field(default=5)

    # Postgres
    postgres_host: str = Field(default="postgres")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="falcon_inference")
    postgres_user: str = Field(default="falcon")
    postgres_password: str = Field(default="falcon_dev_password_change_in_prod")
    postgres_pool_size: int = Field(default=20)
    postgres_max_overflow: int = Field(default=10)
    postgres_pool_timeout: int = Field(default=30)
    postgres_pool_recycle: int = Field(default=3600)

    # Cache
    cache_ttl_seconds: int = Field(default=3600)
    cache_enabled: bool = Field(default=True)

    # Idempotency
    idempotency_enabled: bool = Field(default=True)
    idempotency_ttl_seconds: int = Field(default=86400)

    # Circuit Breaker
    circuit_breaker_enabled: bool = Field(default=True)
    circuit_breaker_failure_threshold: int = Field(default=5)
    circuit_breaker_timeout_seconds: int = Field(default=60)
    circuit_breaker_half_open_attempts: int = Field(default=3)

    # Retry
    retry_enabled: bool = Field(default=True)
    retry_max_attempts: int = Field(default=3)
    retry_base_delay_ms: int = Field(default=100)
    retry_max_delay_ms: int = Field(default=5000)
    retry_exponential_base: int = Field(default=2)

    # Timeouts
    request_timeout_seconds: int = Field(default=30)
    inference_timeout_seconds: int = Field(default=10)
    redis_operation_timeout_seconds: int = Field(default=2)
    postgres_operation_timeout_seconds: int = Field(default=5)

    # Graceful Shutdown
    graceful_shutdown_timeout_seconds: int = Field(default=30)

    # Monitoring
    enable_metrics: bool = Field(default=True)
    metrics_port: int = Field(default=8000)
    enable_tracing: bool = Field(default=False)

    # Rate Limiting
    rate_limit_enabled: bool = Field(default=True)
    rate_limit_per_minute: int = Field(default=1000)

    # Debug
    debug_memory_growth: bool = Field(default=False)
    debug_memory_growth_mb_per_request: int = Field(default=0)

    @property
    def database_url(self) -> str:
        """Get database URL."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        """Get async database URL."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
