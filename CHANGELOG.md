# Changelog

All notable changes to Falcon are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-02-01

### Added
- Production ML inference API: `POST /infer` for single-text sentiment classification (negative, neutral, positive)
- Batch inference endpoint: `POST /infer/batch` supporting up to 50 texts per request
- Nginx load balancer routing across multiple FastAPI workers (least-connections algorithm)
- Redis response caching keyed by normalized input for sub-millisecond cache hits
- Redis-backed idempotency via `X-Idempotency-Key` header to prevent duplicate processing
- PostgreSQL async request logging with in-memory buffer (max 1,000 entries) for Postgres failover
- Circuit breaker: opens on 5 consecutive failures, 60s timeout, half-open recovery probe
- Exponential backoff retry: 3 attempts, 100ms–5s delay range
- Graceful shutdown: SIGTERM handler drains in-flight requests and flushes log buffer
- Prometheus metrics: 20+ metrics including latency histograms, cache hit ratio, circuit breaker state, dropped log count
- Grafana pre-provisioned dashboard: RPS, p50/p95/p99 latency, error rate, cache hit ratio, worker health
- Prometheus alert rules: high p95 latency, error rate spike, worker down, Redis/Postgres unhealthy
- k6 load testing suite: baseline (50 VUs/5 min), stress (ramp to 500 VUs), spike (10→300 VUs), soak (100 VUs/10 min)
- Failure injection scripts: `kill_worker.sh`, `redis_down.sh`, `postgres_slow.sh`, `cpu_spike.sh`
- Docker Compose local dev stack: API workers, Nginx, Redis, PostgreSQL, Prometheus, Grafana
- GitHub Actions CI/CD pipeline with automated deployment to GitHub Pages (demo site)
- Full documentation suite: `RUNBOOK.md`, `CAPACITY_PLAN.md`, `SECURITY.md`, `TRADEOFFS.md`, `PERFORMANCE_NOTES.md`, `UBUNTU_DEPLOYMENT.md`

### Performance
- p95 latency reduced by 30% vs single-worker baseline under 500 VU load
- Cache hit ratio: 70%+ on repeated inference requests
- Graceful shutdown completes within configured `GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS`
- Circuit breaker eliminates cascading failure propagation to upstream clients

### Infrastructure
- Python 3.11 runtime
- FastAPI 0.109 + Uvicorn 0.27
- Nginx 1.25
- Redis 7
- PostgreSQL 15
- Prometheus 2.48 + Grafana 10.2

---

## [Unreleased]

### Planned
- GPU inference support with CUDA-accelerated model serving
- Multi-model registry with hot-swap capability
- Horizontal autoscaling via Kubernetes HPA
- OpenTelemetry distributed tracing integration
- gRPC endpoint alongside REST for lower-latency clients
- A/B testing framework for model version comparison
- Token-based authentication (JWT) for API access control
