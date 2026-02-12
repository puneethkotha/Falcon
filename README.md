# Falcon ML Inference Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green.svg)](https://fastapi.tiangolo.com/)

A **production-grade ML inference platform** demonstrating Meta Production Engineering principles: Linux system expertise, networking, observability, reliability engineering, and capacity planning.

## 🎯 Purpose

This project showcases Production Engineering skills through a realistic ML inference service with:

- **Infrastructure-first design**: Focus on reliability, observability, and operations
- **Production-ready patterns**: Circuit breakers, retries, graceful shutdown, health checks
- **Comprehensive observability**: Prometheus metrics, Grafana dashboards, structured logging
- **Failure resilience**: Automatic fallbacks, load balancing, dependency isolation
- **Operational excellence**: Runbooks, capacity planning, load testing, failure injection

## 🏗️ Architecture

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

## 🚀 Quick Start

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- Make (optional, for convenience)
- k6 (for load testing): `brew install k6` or see [k6.io](https://k6.io/docs/getting-started/installation/)

### Local Setup

```bash
# 1. Clone the repository
git clone https://github.com/puneethkotha/Falcon.git
cd Falcon

# 2. Train the ML model
python scripts/train_model.py

# 3. Start the platform
make up
# Or: docker compose up -d

# 4. Wait for services to be healthy (~30 seconds)
make check-health

# 5. Run the demo
make demo
```

### Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| **API** | http://localhost/infer | - |
| **Health** | http://localhost/healthz | - |
| **Metrics** | http://localhost/metrics | - |
| **Grafana** | http://localhost:3000 | admin / admin_change_in_prod |
| **Prometheus** | http://localhost:9090 | - |

## 📡 API Endpoints

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

## 🔬 Key Features

### 1. **Reliability Engineering**

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

### 2. **Observability**

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

### 3. **Load Testing**

Four comprehensive load test scenarios:

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

### 4. **Failure Injection**

Test system resilience with failure scenarios:

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

## 📊 Performance

### Expected Baseline (3 workers, local Docker)

- **RPS**: 200-300 requests/second
- **p50 Latency**: 20-50ms
- **p95 Latency**: 100-200ms
- **p99 Latency**: 200-500ms
- **Error Rate**: <1%
- **Cache Hit Rate**: 60-80% (after warm-up)

### Capacity Planning

See [docs/CAPACITY_PLAN.md](docs/CAPACITY_PLAN.md) for detailed analysis.

## 🛠️ Development

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

## 📖 Documentation

- **[RUNBOOK.md](docs/RUNBOOK.md)** - On-call guide with 6+ incident scenarios
- **[CAPACITY_PLAN.md](docs/CAPACITY_PLAN.md)** - Resource planning and scaling
- **[SECURITY.md](docs/SECURITY.md)** - Security considerations
- **[TRADEOFFS.md](docs/TRADEOFFS.md)** - Design decisions and alternatives
- **[POSTMORTEM_TEMPLATE.md](docs/POSTMORTEM_TEMPLATE.md)** - Incident postmortem template

## 🐧 Linux Deployment

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

## 🔍 Debugging

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

## 🎓 Production Engineering Demonstrations

This project demonstrates:

### Linux/Unix Skills
- ✅ Docker containerization
- ✅ systemd service management
- ✅ Network diagnostics (ss, lsof, curl)
- ✅ Log management (journalctl, structured logging)
- ✅ Process management (signals, graceful shutdown)
- ✅ Shell scripting for operations

### Networking
- ✅ Nginx L7 load balancing
- ✅ Health checks and failover
- ✅ Connection pooling
- ✅ Timeout management
- ✅ Rate limiting

### Observability
- ✅ Prometheus metrics collection
- ✅ Grafana dashboards
- ✅ Alert rules
- ✅ Structured logging
- ✅ Request tracing (request IDs)

### Reliability
- ✅ Circuit breakers
- ✅ Retry with exponential backoff
- ✅ Graceful degradation
- ✅ Idempotency
- ✅ Fallback strategies
- ✅ Health checks

### Capacity Planning
- ✅ Load testing
- ✅ Resource requirements
- ✅ Scaling strategies
- ✅ Bottleneck analysis

### Operational Excellence
- ✅ Runbooks for common incidents
- ✅ Failure injection testing
- ✅ Postmortem templates
- ✅ Documentation

## 🤝 Contributing

This is a portfolio project demonstrating Production Engineering skills. For educational or professional reference only.

## 📝 License

MIT License - See [LICENSE](LICENSE) file for details.

## 👤 Author

**Puneeth Kotha**
- GitHub: [@puneethkotha](https://github.com/puneethkotha)
- Project: [Falcon ML Inference Platform](https://github.com/puneethkotha/Falcon)

## 🙏 Acknowledgments

This project demonstrates patterns and practices inspired by:
- Meta Production Engineering principles
- Site Reliability Engineering (SRE) best practices
- Cloud Native patterns
- Microservices reliability patterns

---

**Built with ❤️ for Production Engineering excellence**
