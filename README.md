# Falcon ML Inference Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green.svg)](https://fastapi.tiangolo.com/)

Production ML inference service focused on infrastructure and reliability engineering. This is less about ML research and more about building systems that actually work in production.

## What This Is

This demonstrates how to build and operate ML services at scale. The focus is infrastructure-first: circuit breakers, retry logic, graceful degradation, observability, and operational tooling.

The ML model itself is deliberately simple (scikit-learn text classifier) because the interesting engineering problems are in everything around it—deployment, reliability, monitoring, debugging, and keeping it running when dependencies fail.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        NGINX Load Balancer                   │
│                   (Reverse Proxy + L7 LB)                    │
└────────┬─────────────┬─────────────┬──────────────────────
│ │                    │
         v                         v                         v
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Worker 1      │     │   Worker 2      │     │   Worker 3      │
│  FastAPI        │     │  FastAPI        │     │  FastAPI        │
│  + Uvicorn      │     │  + Uvicorn      │     │  + Uvicorn      │
│  + ML Model     │     │  + ML Model     │     │  + ML Model     │
└────┬────────┬───┘     └────┬────────┬───┘     └────┬────────┬───┘
     │        │              │        │              │        │
     │        └──────────────┴────────┴──────────────┘        │
     │                       │                                │
     v                       v                                v
┌─────────────┐     ┌──────────────┐            ┌──────────────────┐
│   Redis     │     │  PostgreSQL  │            │   Prometheus     │
│  (Cache +   │     │  (Request    │            │   (Metrics)      │
│   Dedupe)   │     │   Logging)   │            └────────┬─────────┘
└─────────────┘     └──────────────┘                     │
                                                         v
                                                ┌──────────────────┐
                                                │    Grafana       │
                                                │  (Dashboards)    │
                                                └──────────────────┘
```

### Request Flow

1. **Client** sends POST to `/infer` through Nginx
2. **Nginx** load balances to healthy worker (least connections)
3. **Worker** checks:
   - Idempotency key (Redis) - skip if duplicate
   - Response cache (Redis) - return if cached
4. **Worker** performs ML inference if needed
5. **Worker** stores result in cache (Redis)
6. **Worker** logs request to database (Postgres) - non-blocking with fallback
7. **Worker** returns response to client

## Quick Start

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- Make (optional, for convenience)
- k6 (for load testing): `brew install k6` or see [k6.io](https://k6.io/docs/getting-started/installation/)

### Local Setup

```bash
# Clone and start
git clone https://github.com/puneethkotha/Falcon.git
cd Falcon

# Train the model (or it'll auto-generate a dummy one)
python scripts/train_model.py

# Start everything
make up

# Wait ~30 seconds, then verify
make check-health

# Test it
curl -X POST http://localhost/infer \
  -H "Content-Type: application/json" \
  -d '{"text": "This product is great!"}'

# Check dashboards
# Grafana: http://localhost:3000 (default login: admin/admin)
# Prometheus: http://localhost:9090
```

## API Endpoints

### POST /infer

Perform ML inference on input text.

**Request:**
```bash
curl -X POST http://localhost/infer \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: unique-key-123" \
  -d '{
    "text": "This product is absolutely amazing!"
  }'
```

**Response:**
```json
{
  "prediction": "positive",
  "confidence": 0.9234,
  "probabilities": {
    "negative": 0.0123,
    "neutral": 0.0643,
    "positive": 0.9234
  },
  "cache_hit": false,
  "worker_id": "worker-1",
  "processing_time_ms": 45.23,
  "idempotency_hit": false
}
```

### GET /healthz

Liveness check - returns 200 if service is alive.

```bash
curl http://localhost/healthz
```

### GET /readyz

Readiness check - returns 200 if service is ready to accept traffic.

```bash
curl http://localhost/readyz
```

### GET /metrics

Prometheus metrics endpoint.

```bash
curl http://localhost/metrics
```

## What's Actually Implemented

### Reliability Engineering

#### Circuit Breaker
- Automatically opens when dependency fails repeatedly
- Half-open state for gradual recovery
- Per-dependency (Redis, Postgres)
- Configurable thresholds

#### Retry with Exponential Backoff
- Automatic retries for transient failures
- Exponential backoff to prevent thundering herd
- Configurable max attempts and delays

#### Graceful Shutdown
- SIGTERM handler stops accepting new requests
- Waits for in-flight requests to complete
- Flushes buffered logs before exit
- Configurable timeout

#### Idempotency
- Client-provided idempotency keys via header
- Deduplication for repeated requests
- 24-hour key retention (configurable)

#### Fallback Behaviors
- **Redis down**: Proceed without cache, increment metrics
- **Postgres down**: Buffer logs in memory (1000 max), auto-flush on recovery
- **Worker down**: Nginx routes to healthy workers

### Observability

#### Prometheus Metrics

**Request Metrics:**
- `inference_requests_total` - Total requests by status and cache hit
- `inference_duration_seconds` - Request latency histogram
- `inference_errors_total` - Errors by type

**Cache Metrics:**
- `cache_hits_total` / `cache_misses_total`
- `cache_errors_total`

**Circuit Breaker:**
- `circuit_breaker_state` - Current state (0=closed, 1=open, 2=half_open)
- `circuit_breaker_failures_total`
- `circuit_breaker_successes_total`

**Database:**
- `db_operations_total` - Operations by type and status
- `db_operation_duration_seconds` - Query latency
- `dropped_logs_total` - Logs dropped when DB unavailable

**System:**
- `memory_usage_bytes` - Worker memory usage
- `retry_attempts_total` - Retry count by operation

#### Grafana Dashboards

Pre-configured dashboard with panels for:
- Request rate (RPS) by worker
- Latency percentiles (p50, p95, p99)
- Error rate
- Cache hit rate
- Worker memory usage
- Circuit breaker state
- Database operation latency

#### Structured JSON Logging

All logs are structured JSON with:
- Request ID
- Worker ID
- Timestamp
- Log level
- Context fields

```json
{
  "timestamp": "2026-02-12T10:30:45.123Z",
  "level": "INFO",
  "logger": "app.api.routes",
  "message": "Inference completed",
  "worker_id": "worker-1",
  "request_id": "abc-123",
  "inference_time_ms": 42.5
}
```

### Load Testing

Four k6 test scenarios because you need more than "it works on my laptop":

```bash
# Baseline (50 VUs, 5 min)
make load-test-baseline

# Stress (ramp to 500 VUs, 10 min)
make load-test-stress

# Spike (sudden 10→300 VUs)
make load-test-spike

# Soak (100 VUs, 10 min)
make load-test-soak
```

### Failure Injection

Scripts to break things on purpose and watch how the system handles it:

```bash
# Kill one worker - verify failover
make failure-inject-kill-worker

# Stop Redis - verify fallback
make failure-inject-redis-down

# Slow Postgres queries - verify buffering
make failure-inject-postgres-slow

# CPU spike on worker - verify load distribution
make failure-inject-cpu-spike

# Memory growth - verify monitoring
make failure-inject-memory-growth
```

## Performance

On a decent laptop with 3 workers, expect around 200-300 RPS with p95 latency under 200ms. Cache hit rate climbs to 60-80% after warm-up, which makes a big difference for repeated queries.

See [docs/CAPACITY_PLAN.md](docs/CAPACITY_PLAN.md) for the full capacity analysis, including how to scale beyond single-server, what bottlenecks to watch for, and why I chose certain timeout values.

## Development

### Project Structure

```
falcon-ml-inference-platform/
├── app/
│   ├── api/              # API routes
│   ├── core/             # Config, logging, metrics
│   ├── models/           # Pydantic schemas, DB models
│   ├── services/         # Business logic (Redis, DB, inference)
│   ├── utils/            # Circuit breaker, retry, hashing
│   └── middleware/       # Request ID, etc.
├── deploy/               # Deployment files (systemd, Ubuntu guide)
├── docs/                 # Documentation
├── grafana/              # Grafana provisioning and dashboards
├── init-db/              # Database initialization scripts
├── models/               # Trained ML models
├── nginx/                # Nginx configuration
├── prometheus/           # Prometheus config and alerts
├── scripts/              # Utility scripts (train, failure injection)
├── tests/
│   ├── load/            # k6 load test scripts
│   ├── unit/            # Unit tests
│   └── integration/     # Integration tests
├── docker-compose.yml    # Docker Compose configuration
├── Dockerfile            # Application container
├── Makefile              # Convenience commands
└── requirements.txt      # Python dependencies
```

### Running Tests

```bash
# Unit tests
make test

# Integration tests
make test-integration

# Type checking
make type-check

# Linting
make lint

# Format code
make format
```

### Environment Variables

Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
```

Key configurations:
- `CIRCUIT_BREAKER_FAILURE_THRESHOLD=5` - Failures before opening
- `RETRY_MAX_ATTEMPTS=3` - Max retry attempts
- `CACHE_TTL_SECONDS=3600` - Cache TTL
- `GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS=30` - Shutdown timeout

## Documentation

Written like actual engineering docs, not marketing material:

- **[RUNBOOK.md](docs/RUNBOOK.md)** - What to do when things break at 3am. Six incident scenarios with actual commands.
- **[CAPACITY_PLAN.md](docs/CAPACITY_PLAN.md)** - How to figure out how many workers you need and when to scale.
- **[SECURITY.md](docs/SECURITY.md)** - Threat model and what security controls are actually implemented.
- **[TRADEOFFS.md](docs/TRADEOFFS.md)** - Why I chose X over Y, with honest pros/cons.
- **[POSTMORTEM_TEMPLATE.md](docs/POSTMORTEM_TEMPLATE.md)** - Template for writing incident postmortems.
- **[PERFORMANCE_NOTES.md](docs/PERFORMANCE_NOTES.md)** - Load testing methodology and tuning results.

## Deployment

### Ubuntu 22.04 on EC2

See [deploy/UBUNTU_DEPLOYMENT.md](deploy/UBUNTU_DEPLOYMENT.md) for complete guide.

Quick steps:
```bash
# 1. Install Docker
curl -fsSL https://get.docker.com | sh

# 2. Clone repo and setup
git clone https://github.com/puneethkotha/Falcon.git
cd Falcon
make train-model

# 3. Configure firewall
sudo ufw allow 80/tcp
sudo ufw allow 3000/tcp
sudo ufw allow 9090/tcp

# 4. Start services
make up

# 5. Verify
make check-health
```

### Systemd Integration

See [deploy/systemd/](deploy/systemd/) for:
- Service unit files
- Auto-start on boot
- Journald integration
- Service management

## Debugging

### View Logs

```bash
# All services
make logs

# Specific service
docker compose logs -f worker-1

# With journalctl (if using systemd)
sudo journalctl -u falcon-inference -f

# Structured log query
docker compose logs worker-1 | jq 'select(.level=="ERROR")'
```

### Network Debugging

```bash
# Check listening ports
ss -tlnp | grep -E '(80|3000|5432|6379|9090)'

# Check connections
lsof -i :80

# Test endpoint
curl -v http://localhost/healthz
```

### Database Queries

```bash
# Open Postgres shell
make db-shell

# Check recent requests
SELECT worker_id, COUNT(*), AVG(processing_time_ms)
FROM inference_logs
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY worker_id;
```

### Redis Inspection

```bash
# Open Redis CLI
make redis-cli

# Check keys
KEYS cache:*
KEYS idempotency:*

# Check memory
INFO memory
```

## What This Actually Shows

**Linux/Unix basics**: Docker, systemd, network debugging with ss/lsof, log management with journalctl, signal handling for graceful shutdown.

**Networking**: L7 load balancing with Nginx, connection pooling, health checks, rate limiting, understanding timeout budgets.

**Observability**: Prometheus metrics (20+ custom metrics), Grafana dashboards, alert rules that actually make sense, structured JSON logging.

**Reliability patterns**: Circuit breakers with half-open states, retry with exponential backoff, graceful degradation when dependencies fail, idempotency for duplicate requests.

**Capacity planning**: Load testing methodology with k6, understanding bottlenecks (spoiler: usually CPU or DB), how to figure out how many workers you need.

**Operations**: Runbooks for common incidents, failure injection testing, knowing how to debug production issues at 3am.

## License

MIT License - See [LICENSE](LICENSE) file.

## Author

Puneeth Kotha ([@puneethkotha](https://github.com/puneethkotha))

## Notes

This implements patterns I've seen work well in production systems—circuit breakers, retry logic, observability, operational tooling. Not everything here is novel; most of it is intentionally boring and proven.

The ML model is deliberately trivial (scikit-learn text sentiment) because the interesting part isn't the model, it's everything around it: how do you deploy it reliably, observe it, debug it, scale it, and keep it running when things break?

Inspired by production engineering practices at companies that run services at scale (Meta, Google, etc.) and SRE principles from people who've actually been paged at 3am.
