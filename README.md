# Falcon

[![Deploy](https://github.com/puneethkotha/Falcon/actions/workflows/pages.yml/badge.svg)](https://github.com/puneethkotha/Falcon/actions/workflows/pages.yml)
[Live Demo](https://puneethkotha.github.io/Falcon/) | [GitHub](https://github.com/puneethkotha/Falcon)

Production ML inference platform. Nginx load balances across multiple FastAPI workers; Redis caches responses and handles idempotency; PostgreSQL logs requests. Circuit breakers, retries, graceful shutdown, and Prometheus/Grafana observability.

---

**Demo site:** `web/` deploys via GitHub Actions. Enable in Settings > Pages > Source: GitHub Actions.

## Tech Stack

| Layer | Technology | Version |
|-------|------------|---------|
| API | FastAPI, Uvicorn | 0.109, 0.27 |
| Load balancer | Nginx | 1.25 |
| Cache | Redis | 7 |
| Database | PostgreSQL | 15 |
| Metrics | Prometheus, Grafana | 2.48, 10.2 |
| Load testing | k6 | - |
| Runtime | Python | 3.11 |
| Containers | Docker, Docker Compose | - |

---

## Key Capabilities

### Inference API

- `POST /infer` – Text sentiment classification (negative, neutral, positive)
- `X-Idempotency-Key` header for request deduplication
- Response cache keyed by normalized input
- Processing time, worker ID, cache hit flag in response

### Reliability

| Feature | Implementation |
|---------|----------------|
| Circuit breaker | Opens on 5 failures; 60s timeout; half-open recovery |
| Retry | Exponential backoff (3 attempts, 100ms–5s) |
| Graceful shutdown | SIGTERM handler; drains in-flight; flushes log buffer |
| Fallbacks | Redis down → proceed without cache; Postgres down → buffer logs (max 1000) |

### Observability

- Prometheus: 20+ metrics (latency histograms, cache hits, circuit breaker state, dropped logs)
- Grafana: Pre-provisioned dashboard (RPS, p50/p95/p99, error rate, cache hit ratio)
- Alerts: High p95, error spike, worker down, Redis/Postgres unhealthy

---

## Quick Start

**Prerequisites:** Docker 20.10+, Docker Compose 2.0+

```bash
# 1. Clone
git clone https://github.com/puneethkotha/Falcon.git
cd Falcon

# 2. Train model (or auto-generates dummy)
python scripts/train_model.py

# 3. Start
make up

# 4. Verify
make check-health

# 5. Test
curl -X POST http://localhost/infer \
  -H "Content-Type: application/json" \
  -d '{"text": "This product is great!"}'
```

Grafana: `localhost:3000` · Prometheus: `localhost:9090`

---

## Load Testing

```bash
make load-test-baseline   # 50 VUs, 5 min
make load-test-stress     # Ramp to 500 VUs
make load-test-spike      # 10→300 VU spike
make load-test-soak       # 100 VUs, 10 min
```

---

## Failure Injection

```bash
./scripts/kill_worker.sh       # Kill one worker; verify failover
./scripts/redis_down.sh       # Stop Redis; verify fallback
./scripts/postgres_slow.sh    # Slow DB; verify buffering
./scripts/cpu_spike.sh        # CPU load; verify load distribution
```

---

## Architecture

```
Client → Nginx (L7 LB) → Worker 1/2/3 (FastAPI + model)
                              ↓
                    Redis (cache, idempotency)
                    PostgreSQL (request logs)
                    Prometheus → Grafana
```

### Request flow

1. Client POST to `/infer`
2. Nginx forwards to worker (least connections)
3. Worker checks idempotency (Redis); returns cached if duplicate
4. Worker checks response cache (Redis); returns if hit
5. Worker runs inference; caches result; logs to Postgres (async); returns

---

## Project Layout

```
├── app/           # FastAPI app, API routes, services
├── nginx/         # Nginx config
├── prometheus/    # Prometheus + alert rules
├── grafana/       # Dashboards, provisioning
├── deploy/        # Systemd units, Ubuntu guide
├── docs/          # Runbook, capacity plan, security
├── scripts/       # Train model, failure injection
├── web/           # Demo site (GitHub Pages)
├── tests/load/    # k6 scripts
└── docker-compose.yml
```

---

## Documentation

| Doc | Purpose |
|-----|---------|
| [RUNBOOK.md](docs/RUNBOOK.md) | Incident scenarios and commands |
| [CAPACITY_PLAN.md](docs/CAPACITY_PLAN.md) | Scaling, resources, timeouts |
| [SECURITY.md](docs/SECURITY.md) | Threat model, controls |
| [TRADEOFFS.md](docs/TRADEOFFS.md) | Design decisions |
| [PERFORMANCE_NOTES.md](docs/PERFORMANCE_NOTES.md) | Load testing and tuning |
| [UBUNTU_DEPLOYMENT.md](deploy/UBUNTU_DEPLOYMENT.md) | Full deployment guide |

---

## Environment

Copy `.env.example` to `.env`. Key vars: `CIRCUIT_BREAKER_FAILURE_THRESHOLD`, `RETRY_MAX_ATTEMPTS`, `CACHE_TTL_SECONDS`, `GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS`.

---

## License

MIT © Puneeth Kotha
