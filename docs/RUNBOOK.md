# Falcon ML Inference Platform - Operations Runbook

## 📋 Overview

This runbook provides step-by-step procedures for diagnosing and resolving common incidents in the Falcon ML Inference Platform.

**Target Audience**: On-call engineers, SREs, Production Engineers

**Prerequisites**:
- Access to production servers
- Docker and docker-compose CLI
- kubectl (if using Kubernetes)
- Access to Grafana dashboards
- Access to logs (journalctl or log aggregation system)

---

## 🚨 Incident Response Workflow

1. **Detect**: Alert fires or user report
2. **Assess**: Check dashboards and metrics
3. **Diagnose**: Follow runbook procedures
4. **Mitigate**: Apply fix or workaround
5. **Monitor**: Verify resolution
6. **Document**: Create incident report

---

## 📊 Key Dashboards & Commands

### Quick Health Check
```bash
# Check all services
make check-health

# View metrics
curl -s http://localhost/metrics | grep -E "(inference_requests|error)"

# Check worker status
docker ps --filter name=falcon-worker
```

### Access Grafana
- URL: http://localhost:3000 (or production URL)
- Dashboard: "Falcon ML Inference Platform"
- Key panels: RPS, Latency, Error Rate, Circuit Breaker State

### Log Access
```bash
# Structured logs
docker compose logs -f worker-1 | jq 'select(.level=="ERROR")'

# All workers
docker compose logs -f worker-1 worker-2 worker-3

# With journalctl (systemd)
sudo journalctl -u falcon-inference -f --output=json | jq
```

---

## 🔥 Incident #1: High Latency (P95 > 1s)

### Symptoms
- Prometheus alert: `HighP95Latency`
- Users reporting slow responses
- Grafana: P95 latency spike

### Likely Causes
1. Database slowness
2. Redis slowness
3. CPU/memory pressure on workers
4. Network issues
5. Model inference bottleneck

### Diagnosis Steps

**Step 1: Check basic metrics**
```bash
# Check current latency
curl -s http://localhost/metrics | grep "inference_duration_seconds"

# Output shows histogram buckets and quantiles
```

**Step 2: Identify bottleneck**
```bash
# Check database latency
curl -s http://localhost/metrics | grep "db_operation_duration"

# Check cache hit rate (low = more inference load)
curl -s http://localhost/metrics | grep "cache_hits_total\|cache_misses_total"

# Check worker CPU/memory
docker stats --no-stream falcon-worker-1 falcon-worker-2 falcon-worker-3
```

**Step 3: Check external dependencies**
```bash
# Test Redis
docker exec falcon-redis redis-cli ping
docker exec falcon-redis redis-cli --latency-history

# Test Postgres
docker exec falcon-postgres pg_isready -U falcon
docker exec falcon-postgres psql -U falcon -d falcon_inference -c \
  "SELECT COUNT(*) FROM inference_logs WHERE created_at > NOW() - INTERVAL '1 minute';"
```

**Step 4: Check logs for errors**
```bash
# Look for timeout errors
docker compose logs worker-1 --since 10m | grep -i "timeout\|slow"

# Look for retry attempts
docker compose logs worker-1 --since 10m | grep -i "retry"
```

### Resolution Actions

**If Database is slow:**
```bash
# Check slow queries
docker exec falcon-postgres psql -U falcon -d falcon_inference -c \
  "SELECT pid, now() - query_start as duration, query 
   FROM pg_stat_activity 
   WHERE state = 'active' AND query NOT LIKE '%pg_stat_activity%'
   ORDER BY duration DESC LIMIT 10;"

# Check connections
docker exec falcon-postgres psql -U falcon -d falcon_inference -c \
  "SELECT count(*) FROM pg_stat_activity;"

# If needed, restart Postgres (will cause brief downtime)
docker compose restart postgres
```

**If Redis is slow:**
```bash
# Check Redis memory
docker exec falcon-redis redis-cli INFO memory

# Check slow log
docker exec falcon-redis redis-cli SLOWLOG GET 10

# If needed, restart Redis (will clear cache)
docker compose restart redis
```

**If Workers are overloaded:**
```bash
# Scale up workers
docker compose up -d --scale worker-1=5

# Or add more capacity (edit docker-compose.yml)
# Then: docker compose up -d
```

**If Cache hit rate is low:**
```bash
# Increase cache TTL (edit .env)
CACHE_TTL_SECONDS=7200  # Increase from 3600

# Restart workers to apply
docker compose restart worker-1 worker-2 worker-3
```

### Verification
```bash
# Monitor latency improvement
watch -n 5 'curl -s http://localhost/metrics | grep "inference_duration_seconds" | grep quantile'

# Check Grafana dashboard
# Verify P95 returns to < 1s
```

### Escalation
If latency persists after 15 minutes:
- Escalate to senior SRE
- Consider enabling maintenance mode
- Check for upstream issues (network, DNS)

---

## 🔥 Incident #2: High Error Rate (>5%)

### Symptoms
- Prometheus alert: `HighErrorRate` or `VeryHighErrorRate`
- 5xx responses increasing
- Users reporting failures

### Likely Causes
1. Model loading failure
2. Redis/Postgres unavailable
3. Out of memory
4. Configuration error
5. Bad deployment

### Diagnosis Steps

**Step 1: Check error types**
```bash
# Get error breakdown
curl -s http://localhost/metrics | grep "inference_errors_total"

# Check HTTP status codes in logs
docker compose logs worker-1 --since 10m | jq 'select(.level=="ERROR")'
```

**Step 2: Check worker health**
```bash
# Test each worker directly
curl -s http://localhost:8000/healthz  # worker-1
curl -s http://localhost:8001/healthz  # worker-2 (if exposed)
curl -s http://localhost:8002/healthz  # worker-3 (if exposed)

# Via Nginx
curl -s http://localhost/healthz
```

**Step 3: Check readiness**
```bash
# Readiness includes dependency checks
curl -s http://localhost/readyz | jq
# Look for: model_loaded, redis_available, database_available
```

**Step 4: Check circuit breaker state**
```bash
# Check if circuit breakers are open
curl -s http://localhost/metrics | grep "circuit_breaker_state"
# 0 = closed (good)
# 1 = open (dependency failing)
# 2 = half-open (recovering)
```

### Resolution Actions

**If Model not loaded:**
```bash
# Check model file exists
docker exec falcon-worker-1 ls -lh /app/models/classifier.pkl

# Restart worker to reload model
docker compose restart worker-1

# If model file missing, retrain
python scripts/train_model.py
docker compose restart worker-1 worker-2 worker-3
```

**If Redis unavailable:**
```bash
# Check Redis status
docker exec falcon-redis redis-cli ping

# If down, restart
docker compose restart redis

# Workers should automatically recover via circuit breaker
# Monitor: curl -s http://localhost/metrics | grep "circuit_breaker_state.*redis"
```

**If Postgres unavailable:**
```bash
# Check Postgres status
docker exec falcon-postgres pg_isready -U falcon

# If down, restart
docker compose restart postgres

# Check if logs are being buffered
curl -s http://localhost/metrics | grep "dropped_logs_total"
```

**If OOM (Out of Memory):**
```bash
# Check memory usage
docker stats --no-stream

# Check for memory leak
docker compose logs worker-1 | grep -i "memory"

# Verify debug flags are OFF
docker exec falcon-worker-1 printenv | grep DEBUG_MEMORY_GROWTH
# Should be: DEBUG_MEMORY_GROWTH=false

# Restart affected worker
docker compose restart worker-1
```

**If Bad deployment:**
```bash
# Rollback to previous version
git log --oneline -n 5
git checkout <previous-commit>
docker compose build
docker compose up -d

# Or use Docker image tags
docker tag falcon-worker:latest falcon-worker:rollback
docker compose up -d
```

### Verification
```bash
# Monitor error rate
watch -n 5 'curl -s http://localhost/metrics | grep "inference_requests_total"'

# Send test requests
for i in {1..10}; do
  curl -X POST http://localhost/infer \
    -H "Content-Type: application/json" \
    -d '{"text": "test"}' && echo "✓" || echo "✗"
done
```

---

## 🔥 Incident #3: Worker Crash Loop

### Symptoms
- Worker containers restarting repeatedly
- Docker health checks failing
- Gaps in metrics/logs

### Likely Causes
1. Dependency unavailable at startup
2. Configuration error
3. Port conflict
4. Resource limits exceeded

### Diagnosis Steps

**Step 1: Check container status**
```bash
# See restart count and status
docker ps -a --filter name=falcon-worker

# Check last exit code
docker inspect falcon-worker-1 --format='{{.State.ExitCode}}'
```

**Step 2: Check logs**
```bash
# View recent logs (including crash)
docker compose logs worker-1 --tail=100

# Look for startup errors
docker compose logs worker-1 | jq 'select(.level=="ERROR" or .level=="CRITICAL")'
```

**Step 3: Check dependencies**
```bash
# Verify Redis is up
docker ps | grep redis

# Verify Postgres is up
docker ps | grep postgres

# Test connectivity from worker network
docker compose exec worker-2 ping -c 2 redis
docker compose exec worker-2 ping -c 2 postgres
```

**Step 4: Check resource limits**
```bash
# Check if hitting memory limit
docker inspect falcon-worker-1 | jq '.[0].HostConfig.Memory'

# Check resource usage
docker stats --no-stream falcon-worker-1
```

### Resolution Actions

**If Dependencies unavailable:**
```bash
# Restart dependencies first
docker compose restart redis postgres

# Wait for healthy
sleep 10

# Then restart worker
docker compose restart worker-1
```

**If Configuration error:**
```bash
# Validate environment variables
docker compose exec worker-2 printenv | grep -E "(REDIS|POSTGRES|MODEL)"

# Check .env file
cat .env | grep -v "^#" | grep -v "^$"

# Fix configuration and restart
docker compose restart worker-1
```

**If Port conflict:**
```bash
# Check what's using the port
ss -tlnp | grep 8000
lsof -i :8000

# Kill conflicting process or change port
# Edit docker-compose.yml to use different ports
```

**If Resource limits:**
```bash
# Increase memory limit in docker-compose.yml
# Add under worker service:
#   deploy:
#     resources:
#       limits:
#         memory: 2G

# Restart
docker compose up -d
```

### Verification
```bash
# Check worker stays up for 5 minutes
docker ps --filter name=falcon-worker-1
sleep 300
docker ps --filter name=falcon-worker-1

# Verify no restarts
docker inspect falcon-worker-1 --format='{{.RestartCount}}'
```

---

## 🔥 Incident #4: Redis Down / Circuit Breaker Open

### Symptoms
- Alert: `CircuitBreakerOpen`
- Cache hit rate drops to 0%
- Logs showing "Redis unavailable"
- Increased fallback metrics

### Likely Causes
1. Redis process crashed
2. Redis out of memory
3. Network partition
4. Redis overloaded

### Diagnosis Steps

**Step 1: Check Redis status**
```bash
# Container status
docker ps | grep redis

# Redis health
docker exec falcon-redis redis-cli ping

# Redis info
docker exec falcon-redis redis-cli INFO
```

**Step 2: Check circuit breaker**
```bash
# Circuit breaker state
curl -s http://localhost/metrics | grep "circuit_breaker_state.*redis"
# 1 = open (blocking requests)

# Failure count
curl -s http://localhost/metrics | grep "circuit_breaker_failures_total.*redis"
```

**Step 3: Check memory**
```bash
# Redis memory usage
docker exec falcon-redis redis-cli INFO memory | grep used_memory_human

# Check maxmemory policy
docker exec falcon-redis redis-cli CONFIG GET maxmemory-policy
```

### Resolution Actions

**If Redis crashed:**
```bash
# Restart Redis
docker compose restart redis

# Wait for healthy
docker exec falcon-redis redis-cli ping

# Circuit breaker will auto-close after timeout (60s default)
```

**If Redis out of memory:**
```bash
# Clear cache
docker exec falcon-redis redis-cli FLUSHDB

# Or increase memory limit in docker-compose.yml
# command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru

# Restart
docker compose up -d redis
```

**If Redis overloaded:**
```bash
# Check slow log
docker exec falcon-redis redis-cli SLOWLOG GET 20

# Check client list
docker exec falcon-redis redis-cli CLIENT LIST

# Check commands/sec
docker exec falcon-redis redis-cli INFO stats | grep instantaneous_ops_per_sec
```

### Impact
- Cache disabled (all requests hit model)
- Idempotency disabled (duplicate requests possible)
- Increased inference latency
- **Service continues operating** (fallback behavior)

### Verification
```bash
# Wait for circuit breaker to close
# Default timeout is 60 seconds

# Monitor state
watch -n 5 'curl -s http://localhost/metrics | grep "circuit_breaker_state.*redis"'

# Verify cache working
curl -X POST http://localhost/infer \
  -H "Content-Type: application/json" \
  -d '{"text": "test cache"}' | jq '.cache_hit'
# First: false, Second: true
```

---

## 🔥 Incident #5: Database Down / Logs Being Dropped

### Symptoms
- Alert: `DatabaseLogsDropped`
- Metrics show `dropped_logs_total` increasing
- Logs showing "Database unavailable"
- Database circuit breaker open

### Likely Causes
1. Postgres crashed
2. Disk full
3. Connection pool exhausted
4. Long-running queries blocking

### Diagnosis Steps

**Step 1: Check Postgres status**
```bash
# Container status
docker ps | grep postgres

# Postgres health
docker exec falcon-postgres pg_isready -U falcon

# Connection count
docker exec falcon-postgres psql -U falcon -d falcon_inference -c \
  "SELECT count(*) FROM pg_stat_activity;"
```

**Step 2: Check disk space**
```bash
# Container disk usage
docker exec falcon-postgres df -h

# Host disk usage
df -h
```

**Step 3: Check dropped logs**
```bash
# How many logs dropped
curl -s http://localhost/metrics | grep "dropped_logs_total"

# Log buffer status (check app logs)
docker compose logs worker-1 | grep -i "buffer"
```

### Resolution Actions

**If Postgres crashed:**
```bash
# Restart Postgres
docker compose restart postgres

# Workers will automatically flush buffered logs
# Monitor flush in logs
docker compose logs -f worker-1 | grep -i "flush"
```

**If Disk full:**
```bash
# Check disk usage
df -h

# Clean up old data (if safe)
docker exec falcon-postgres psql -U falcon -d falcon_inference -c \
  "DELETE FROM inference_logs WHERE created_at < NOW() - INTERVAL '30 days';"

# Vacuum
docker exec falcon-postgres psql -U falcon -d falcon_inference -c "VACUUM ANALYZE;"
```

**If Connection pool exhausted:**
```bash
# Check active connections
docker exec falcon-postgres psql -U falcon -d falcon_inference -c \
  "SELECT state, count(*) FROM pg_stat_activity GROUP BY state;"

# Kill long-running queries
docker exec falcon-postgres psql -U falcon -d falcon_inference -c \
  "SELECT pg_terminate_backend(pid) 
   FROM pg_stat_activity 
   WHERE state = 'active' 
   AND query_start < NOW() - INTERVAL '5 minutes'
   AND query NOT LIKE '%pg_stat_activity%';"

# Increase pool size (edit .env)
POSTGRES_POOL_SIZE=40
docker compose restart worker-1 worker-2 worker-3
```

### Impact
- Logs buffered in memory (max 1000 per worker)
- After buffer full, logs dropped (metric incremented)
- **Inference continues working** (logging is non-blocking)
- Logs auto-flush when DB recovers

### Verification
```bash
# Verify DB is healthy
docker exec falcon-postgres pg_isready -U falcon

# Check logs were flushed
docker compose logs worker-1 | grep "Flushed.*logs"

# Verify new requests are being logged
docker exec falcon-postgres psql -U falcon -d falcon_inference -c \
  "SELECT COUNT(*) FROM inference_logs WHERE created_at > NOW() - INTERVAL '1 minute';"
```

---

## 🔥 Incident #6: Memory Usage Increasing

### Symptoms
- Alert: `HighMemoryUsage`
- Container memory usage growing over time
- Potential OOM kill risk
- Slow GC or swapping

### Likely Causes
1. Memory leak in application
2. DEBUG_MEMORY_GROWTH flag enabled (test mode)
3. Large cache/buffer accumulation
4. No memory limits set

### Diagnosis Steps

**Step 1: Check current memory usage**
```bash
# Real-time memory
docker stats --no-stream falcon-worker-1 falcon-worker-2 falcon-worker-3

# Memory metrics
curl -s http://localhost/metrics | grep "memory_usage_bytes"
```

**Step 2: Check for debug flags**
```bash
# CRITICAL: Check if debug mode is enabled
docker exec falcon-worker-1 printenv | grep DEBUG_MEMORY_GROWTH

# Should be: DEBUG_MEMORY_GROWTH=false
# If true: THIS IS A MEMORY LEAK TEST MODE - DISABLE IMMEDIATELY
```

**Step 3: Check memory trends**
```bash
# View in Grafana
# Dashboard: "Falcon ML Inference Platform"
# Panel: "Worker Memory Usage"
# Look for: steady growth over time vs. sawtooth pattern (normal GC)
```

**Step 4: Check log buffer size**
```bash
# Check if database is down and logs accumulating
curl -s http://localhost/metrics | grep "dropped_logs_total"

# Buffer is limited to 1000 entries per worker
# Check logs for buffer warnings
docker compose logs worker-1 | grep -i "buffer full"
```

### Resolution Actions

**If DEBUG_MEMORY_GROWTH enabled (critical):**
```bash
# IMMEDIATE ACTION REQUIRED
# Edit .env
DEBUG_MEMORY_GROWTH=false
DEBUG_MEMORY_GROWTH_MB_PER_REQUEST=0

# Restart workers
docker compose restart worker-1 worker-2 worker-3

# Verify disabled
docker exec falcon-worker-1 printenv | grep DEBUG_MEMORY_GROWTH
```

**If Database down causing buffer growth:**
```bash
# Fix database (see Incident #5)
docker compose restart postgres

# Workers will flush buffer automatically
```

**If Actual memory leak:**
```bash
# Restart affected worker(s)
docker compose restart worker-1

# Set memory limits (docker-compose.yml)
deploy:
  resources:
    limits:
      memory: 1G
    reservations:
      memory: 512M

# Report bug with memory profile
# In production: take heap dump before restart
```

**If No leak, just needs more memory:**
```bash
# Increase memory limit
# Edit docker-compose.yml
deploy:
  resources:
    limits:
      memory: 2G

# Restart
docker compose up -d
```

### Verification
```bash
# Monitor memory over 15 minutes
for i in {1..15}; do
  docker stats --no-stream falcon-worker-1 | tail -1
  sleep 60
done

# Should see either:
# 1. Stable memory (with GC fluctuations)
# 2. OOM if leak continues (then restart + investigate)
```

---

## 📞 Escalation Contacts

| Severity | Contact | Response Time |
|----------|---------|---------------|
| P0 (Critical) | Senior SRE + Manager | 15 minutes |
| P1 (High) | Senior SRE | 1 hour |
| P2 (Medium) | Team | 4 hours |
| P3 (Low) | Create ticket | Next business day |

## 📚 Additional Resources

- **Metrics**: http://localhost:9090 (Prometheus)
- **Dashboards**: http://localhost:3000 (Grafana)
- **Capacity Plan**: [CAPACITY_PLAN.md](CAPACITY_PLAN.md)
- **Architecture**: [README.md](../README.md)
- **Postmortem Template**: [POSTMORTEM_TEMPLATE.md](POSTMORTEM_TEMPLATE.md)

---

**Last Updated**: 2026-02-12  
**Maintainer**: SRE Team  
**Review Cadence**: Quarterly
