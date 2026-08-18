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

    # Model (legacy sklearn fields retained for the /infer classify fallback tooling)
    model_path: str = Field(default="/app/models/classifier.pkl")
    model_type: str = Field(default="sklearn")
    enable_batching: bool = Field(default=True)
    batch_size: int = Field(default=32)
    batch_timeout_ms: int = Field(default=100)

    # LLM serving engine (vLLM OpenAI-compatible endpoint)
    # Points at the vLLM CPU service in docker-compose by default; switch the
    # base URL to a scale-to-zero GPU endpoint (Modal/RunPod/HF) for the GPU path.
    vllm_base_url: str = Field(default="http://vllm:8000/v1")
    vllm_api_key: str = Field(default="EMPTY")  # OpenAI-compatible servers ignore the value
    model_id: str = Field(default="Qwen/Qwen3-0.6B")  # CPU near-$0 default; Qwen3-1.7B on GPU
    generation_timeout_seconds: int = Field(default=120)  # long generations outlast /infer's 30s budget
    generation_connect_timeout_seconds: int = Field(default=10)
    default_max_tokens: int = Field(default=256)
    default_temperature: float = Field(default=0.7)
    # Constrained classify path used by the backward-compatible /infer route
    classify_max_tokens: int = Field(default=16)
    classify_temperature: float = Field(default=0.0)

    # Online quality observability (async, off the critical path)
    quality_sampling_enabled: bool = Field(default=True)
    quality_sample_rate: float = Field(default=0.1)  # 10% of completions
    quality_queue_maxsize: int = Field(default=1000)
    quality_judge_enabled: bool = Field(default=False)  # requires a judge budget; deterministic checks always run
    quality_judge_model: str = Field(default="Qwen/Qwen3-1.7B")
    quality_refusal_markers: str = Field(
        default="i cannot,i can't,i'm sorry,i am sorry,as an ai,i am unable,i'm unable"
    )

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
