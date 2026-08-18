"""Prometheus metrics."""
from prometheus_client import Counter, Histogram, Gauge, Info
from typing import Optional

# Info metric
app_info = Info("app", "Application info")

# Request counters
inference_requests_total = Counter(
    "inference_requests_total",
    "Total inference requests",
    ["worker_id", "status", "cache_hit"],
)

inference_errors_total = Counter(
    "inference_errors_total",
    "Total inference errors",
    ["worker_id", "error_type"],
)

# Request duration histogram
inference_duration_seconds = Histogram(
    "inference_duration_seconds",
    "Inference request duration in seconds",
    ["worker_id", "cache_hit"],
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0),
)

# Cache metrics
cache_hits_total = Counter(
    "cache_hits_total",
    "Total cache hits",
    ["worker_id"],
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total cache misses",
    ["worker_id"],
)

cache_errors_total = Counter(
    "cache_errors_total",
    "Total cache errors",
    ["worker_id", "operation"],
)

# Idempotency metrics
idempotency_hits_total = Counter(
    "idempotency_hits_total",
    "Total idempotent request hits",
    ["worker_id"],
)

idempotency_misses_total = Counter(
    "idempotency_misses_total",
    "Total idempotent request misses",
    ["worker_id"],
)

# Database metrics
db_operations_total = Counter(
    "db_operations_total",
    "Total database operations",
    ["worker_id", "operation", "status"],
)

db_operation_duration_seconds = Histogram(
    "db_operation_duration_seconds",
    "Database operation duration in seconds",
    ["worker_id", "operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

db_connection_pool_size = Gauge(
    "db_connection_pool_size",
    "Current database connection pool size",
    ["worker_id"],
)

db_connection_pool_available = Gauge(
    "db_connection_pool_available",
    "Available database connections in pool",
    ["worker_id"],
)

# Circuit breaker metrics
circuit_breaker_state = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["worker_id", "dependency"],
)

circuit_breaker_failures_total = Counter(
    "circuit_breaker_failures_total",
    "Total circuit breaker failures",
    ["worker_id", "dependency"],
)

circuit_breaker_successes_total = Counter(
    "circuit_breaker_successes_total",
    "Total circuit breaker successes",
    ["worker_id", "dependency"],
)

# Retry metrics
retry_attempts_total = Counter(
    "retry_attempts_total",
    "Total retry attempts",
    ["worker_id", "operation"],
)

# Model metrics
model_load_duration_seconds = Gauge(
    "model_load_duration_seconds",
    "Model load duration in seconds",
    ["worker_id"],
)

# NOTE: model_inference_batch_size was retired in the LLM-serving upgrade.
# Client-side batch size is meaningless for token streaming; in-flight batch
# depth is now read from the engine via vllm:num_requests_running.

# ---------------------------------------------------------------------------
# LLM token-serving metrics (Falcon-side, per-request timing).
# These let the frontend show live numbers reading only Falcon's /metrics,
# and are reconciled against the engine's own vllm:* series in Grafana.
# ---------------------------------------------------------------------------

# Time to first token: from request dispatch to first streamed chunk.
falcon_ttft_seconds = Histogram(
    "falcon_ttft_seconds",
    "Time to first token in seconds (Falcon-observed, includes proxy hop)",
    ["worker_id"],
    buckets=(0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0),
)

# Inter-token latency: gap between successive streamed chunks (approximates TPOT).
falcon_inter_token_seconds = Histogram(
    "falcon_inter_token_seconds",
    "Inter-token latency in seconds (gap between successive streamed chunks)",
    ["worker_id"],
    buckets=(0.005, 0.01, 0.02, 0.03, 0.05, 0.075, 0.1, 0.2, 0.5, 1.0),
)

# End-to-end generation wall time (dispatch to last chunk).
falcon_generation_duration_seconds = Histogram(
    "falcon_generation_duration_seconds",
    "End-to-end generation duration in seconds (Falcon-observed)",
    ["worker_id"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0),
)

falcon_output_tokens_total = Counter(
    "falcon_output_tokens_total",
    "Total output (completion) tokens streamed by Falcon",
    ["worker_id"],
)

falcon_prompt_tokens_total = Counter(
    "falcon_prompt_tokens_total",
    "Total prompt tokens submitted to the engine",
    ["worker_id"],
)

# ---------------------------------------------------------------------------
# Online quality-observability metrics (async sampler, judge off critical path).
# ---------------------------------------------------------------------------

falcon_quality_sampled_total = Counter(
    "falcon_quality_sampled_total",
    "Completions sampled into the quality queue",
    ["worker_id", "path"],
)

falcon_quality_check_failed_total = Counter(
    "falcon_quality_check_failed_total",
    "Deterministic quality-check failures",
    ["worker_id", "check"],
)

falcon_refusal_total = Counter(
    "falcon_refusal_total",
    "Sampled completions classified as refusals",
    ["worker_id"],
)

falcon_quality_dropped_total = Counter(
    "falcon_quality_dropped_total",
    "Samples dropped because the quality queue was full",
    ["worker_id"],
)

falcon_judge_score = Histogram(
    "falcon_judge_score",
    "LLM-as-judge score for sampled completions (0-1)",
    ["worker_id"],
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

# System metrics
memory_usage_bytes = Gauge(
    "memory_usage_bytes",
    "Current memory usage in bytes",
    ["worker_id"],
)

dropped_logs_total = Counter(
    "dropped_logs_total",
    "Total dropped log entries when database unavailable",
    ["worker_id"],
)

# Fallback metrics
fallback_triggered_total = Counter(
    "fallback_triggered_total",
    "Total fallback triggers",
    ["worker_id", "dependency", "fallback_type"],
)


def init_metrics(worker_id: str, app_name: str, version: str) -> None:
    """Initialize metrics with app info."""
    app_info.info({
        "worker_id": worker_id,
        "app_name": app_name,
        "version": version,
    })
