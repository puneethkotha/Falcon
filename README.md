# Falcon

[![Deploy](https://github.com/puneethkotha/Falcon/actions/workflows/pages.yml/badge.svg)](https://github.com/puneethkotha/Falcon/actions/workflows/pages.yml)
[Live Demo](https://puneethkotha.github.io/Falcon/) | [GitHub](https://github.com/puneethkotha/Falcon)

A reliability chassis that serves a real LLM, instrumented on the metrics that govern
token latency. Nginx load-balances FastAPI workers; each worker streams an
OpenAI-compatible vLLM engine, protected by the same circuit breaker, retry, timeout,
and graceful-drain that guard Redis and Postgres. Token-level metrics (TTFT, inter-token
latency, tokens/sec, KV-cache, queue depth, prefix-cache hit rate) feed Prometheus and
Grafana, and an async sidecar scores a sample of outputs so "200 OK" is separated from
"the output was correct."

The engine is one more protected dependency, not a bypass of the chassis: the breaker
that opens on repeated Redis failures is the same construct that opens on vLLM timeouts.

---

## API

- `POST /v1/chat/completions` - OpenAI-compatible chat, streaming (SSE) or not
- `POST /generate` - Falcon-native streaming generation (SSE)
- `POST /infer` - backward-compatible sentiment classify, re-expressed as a constrained
  LLM call (keeps the legacy k6 baseline and demo working)
- `POST /infer/batch` - batch classify
- `GET /serving/stats` - engine KV/queue/prefix snapshot for the demo pane
- `GET /healthz`, `GET /readyz`, `GET /metrics`

## Tech Stack

| Layer | Technology |
|-------|------------|
| Serving engine | vLLM (OpenAI-compatible): continuous batching, PagedAttention, prefix caching |
| Model | Qwen3-1.7B (GPU) / Qwen3-0.6B (CPU near-$0) |
| API | FastAPI, Uvicorn (streaming SSE) |
| Load balancer | Nginx (least_conn, rate limit, SSE-safe streaming routes) |
| Cache / DB | Redis (response cache, idempotency), PostgreSQL (request + quality logs) |
| Metrics | Prometheus, Grafana (serving, reliability, quality dashboards) |
| Benchmarks | guidellm (frontier), k6 (chassis under load) |
| Hosting | Static frontend on Pages ($0) + Modal scale-to-zero GPU (idle $0) |

---

## Reliability chassis

| Feature | Implementation |
|---------|----------------|
| Circuit breaker | Redis, Postgres, and the vLLM engine; opens on N failures, half-open recovery |
| Retry | Async exponential backoff (guards each protected dependency) |
| Streaming failover | Nginx `proxy_next_upstream`; `proxy_buffering off` on the SSE routes |
| Graceful shutdown | SIGTERM drains in-flight work, flushes the log buffer, closes the engine client |
| Fallbacks | Redis down -> no cache; Postgres down -> buffer logs; engine down -> 502 then 503 once the breaker opens |

## Token-serving metrics

TTFT, inter-token latency / TPOT, output tokens/sec, KV-cache utilization, running-vs-waiting
queue depth, and prefix-cache hit rate, reconciled from Falcon's per-request timing
(`falcon_*`) and the engine's `vllm:*` series. See the Falcon LLM Serving Grafana dashboard.

## Throughput-vs-latency frontier

The headline artifact is a curve of output tokens/sec against TTFT p95 and TPOT p95, swept
from synchronous to saturation with `guidellm`, knee annotated, max-rate-at-SLO marked, plus
cost per 1M output tokens. Harness and reproduction recipe: `docs/frontier/`. The real curve
requires a GPU host and is not fabricated here.

## Online quality (200 OK != correct)

An async sidecar samples 5-10% of completions off the critical path, runs deterministic
checks (refusal, empty/truncated, label/confidence validity), and optionally an LLM judge
(calibrated with Cohen's Kappa). Quality is decoupled from reliability: a degraded model
shows a refusal spike while the reliability dashboard stays green. See
`docs/QUALITY_OBSERVABILITY.md`.

---

## Quick Start

**Prerequisites:** Docker 20.10+, Docker Compose 2.0+ (GPU host for the real engine).

```bash
git clone https://github.com/puneethkotha/Falcon.git
cd Falcon
cp .env.example .env

# Reliability chassis + observability (no GPU required)
make up

# Add the vLLM engine on a GPU host
docker compose --profile gpu up -d vllm
#   or deploy scale-to-zero: modal deploy deploy/modal_app.py, then set VLLM_BASE_URL

# Stream a completion through Nginx
curl -N -X POST http://localhost/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain time to first token.", "max_tokens": 64}'
```

Grafana: `localhost:3000` (serving / reliability / quality) - Prometheus: `localhost:9090`

### No GPU here? Local plumbing

vLLM's CPU backend is x86-avx-only and does not run on Apple Silicon. For local development
and CI, `tools/mock_vllm_server.py` is a labelled OpenAI-compatible test double that exercises
the streaming path, metrics, breaker, and quality sidecar (it is not a benchmark):

```bash
python -m uvicorn tools.mock_vllm_server:app --port 8000
VLLM_BASE_URL=http://localhost:8000/v1 python -m uvicorn app.main:app --port 8001
```

---

## Load Testing & Benchmarks

```bash
make load-test-streaming   # k6 TTFT under a ramp (chassis-level)
make load-test-spike       # 10->300 VU spike; TTFT stability
./benchmarks/guidellm_sweep.sh          # throughput-vs-latency frontier (GPU host)
python benchmarks/plot_frontier.py ...  # plot + cost/1M tokens
```

## Failure Injection

```bash
./scripts/kill_vllm.sh     # kill the engine; 502 -> breaker opens -> 503 -> recovery
./scripts/kill_worker.sh   # kill a worker; verify Nginx failover
./scripts/redis_down.sh    # stop Redis; verify cache fallback
```

---

## Architecture

```
viewer / k6 / guidellm
   | HTTP + SSE
   v
Nginx (least_conn, rate limit, proxy_buffering off for SSE, failover)
   v
FastAPI worker x N
   - idempotency + response cache (Redis)
   - request + quality log (Postgres)
   - CircuitBreaker("vllm") + retry + generation timeout
   - records TTFT / ITL / tokens as it streams
   v
vLLM engine (OpenAI server): continuous batching, PagedAttention, prefix caching
   |
   +--> Prometheus (falcon + vllm metrics) --> Grafana (serving / reliability / quality)
   +--> async quality sidecar (sample -> checks + judge)
```

---

## Documentation

| Doc | Purpose |
|-----|---------|
| [SERVING_LEVERS.md](docs/SERVING_LEVERS.md) | Prefix caching / chunked prefill / speculative decoding: keep-or-kill |
| [QUALITY_OBSERVABILITY.md](docs/QUALITY_OBSERVABILITY.md) | Async sampling, checks, judge calibration, decoupling |
| [frontier/README.md](docs/frontier/README.md) | Throughput-vs-latency frontier reproduction recipe |
| [PERFORMANCE_NOTES.md](docs/PERFORMANCE_NOTES.md) | Pre-upgrade chassis tuning; token-serving evidence method |
| [RUNBOOK.md](docs/RUNBOOK.md) | Incident scenarios and commands |
| [CAPACITY_PLAN.md](docs/CAPACITY_PLAN.md) | Scaling, resources, timeouts |

---

## License

MIT (c) Puneeth Kotha
