# Capacity Planning - Falcon ML Inference Platform

## 📊 Executive Summary

This document provides capacity planning guidance for the Falcon ML Inference Platform, including resource requirements, performance characteristics, and scaling strategies.

**Target SLOs:**
- **Availability**: 99.9% (43 minutes downtime/month)
- **Latency (p95)**: < 500ms
- **Latency (p99)**: < 1000ms
- **Error Rate**: < 0.1%
- **Throughput**: Scales with worker count

---

## 🎯 Performance Baseline

### Single Worker Performance

Based on load testing with the baseline model (scikit-learn text classifier):

| Metric | Value | Notes |
|--------|-------|-------|
| **CPU** | 0.5-1.0 cores | Under load |
| **Memory** | 200-400 MB | Includes model + runtime |
| **RPS (uncached)** | 50-80 | Full inference per request |
| **RPS (cached)** | 200-300 | Cache hit scenario |
| **p50 Latency** | 20-30ms | Cached |
| **p50 Latency** | 50-100ms | Uncached |
| **p95 Latency** | 100-150ms | Cached |
| **p95 Latency** | 200-400ms | Uncached |
| **Model Load Time** | 1-2s | Startup |
| **Model Size** | 5-10 MB | TF-IDF + LogReg |

### Three Worker Cluster (Default)

| Metric | Value | Notes |
|--------|-------|-------|
| **Total CPU** | 1.5-3.0 cores | Combined |
| **Total Memory** | 600MB-1.2GB | Workers only |
| **Max RPS** | 150-240 | Uncached, without degradation |
| **Max RPS** | 600-900 | With 70% cache hit rate |
| **p95 Latency** | 150-300ms | At 150 RPS |
| **Sustained Load** | 100-150 RPS | Recommended |

### Full Stack Resource Requirements

| Component | CPU | Memory | Disk | Network |
|-----------|-----|--------|------|---------|
| **Worker x3** | 3 cores | 1.2 GB | Minimal | Moderate |
| **Nginx** | 0.1 cores | 50 MB | Minimal | High |
| **Redis** | 0.2 cores | 256 MB | 100 MB | Moderate |
| **Postgres** | 0.5 cores | 512 MB | 10 GB | Low |
| **Prometheus** | 0.5 cores | 512 MB | 20 GB | Low |
| **Grafana** | 0.2 cores | 256 MB | 1 GB | Low |
| **cAdvisor** | 0.1 cores | 128 MB | Minimal | Low |
| **TOTAL** | **4.6 cores** | **2.9 GB** | **31 GB** | - |

**Recommended Server:**
- **Development**: 4 vCPU, 8 GB RAM, 50 GB SSD
- **Production**: 8 vCPU, 16 GB RAM, 100 GB SSD (with monitoring)

---

## 📈 Scaling Strategy

### Vertical Scaling (Single Server)

**When to scale vertically:**
- Current workers hitting CPU limits (>80% sustained)
- Memory pressure causing OOM
- Simple to implement (just add resources)

**Limits:**
- Single point of failure
- Limited by server size
- Eventually need horizontal scaling

**How to scale:**
```yaml
# docker-compose.yml
services:
  worker-1:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
```

### Horizontal Scaling (Add Workers)

**When to scale horizontally:**
- Need more than 300 RPS sustained
- Want high availability
- CPU/memory limits reached on current workers

**How to scale:**
```bash
# Quick scale with docker-compose
docker compose up -d --scale worker=6

# Or add explicit workers in docker-compose.yml
# worker-4, worker-5, worker-6...
# Update nginx upstream config
```

**Worker Scaling Table:**

| Workers | Max RPS (uncached) | Max RPS (cached) | Recommended Load | CPU | Memory |
|---------|-------------------|------------------|------------------|-----|--------|
| 1 | 50-80 | 200-300 | 30 RPS | 1 core | 400 MB |
| 3 | 150-240 | 600-900 | 100 RPS | 3 cores | 1.2 GB |
| 5 | 250-400 | 1000-1500 | 200 RPS | 5 cores | 2 GB |
| 10 | 500-800 | 2000-3000 | 500 RPS | 10 cores | 4 GB |

**Formula**: 
- Uncached RPS ≈ 50-80 × workers
- Cached RPS ≈ 200-300 × workers
- Safety factor: Plan for 50-60% of max capacity

### Multi-Server Deployment (Kubernetes/ECS)

**When to use:**
- Need > 10 workers
- High availability requirements
- Multi-region deployment
- Auto-scaling needed

**Architecture:**
```
                    ┌──────────────────┐
                    │   Load Balancer  │
                    │   (ALB/NLB/GCP)  │
                    └────────┬─────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    ┌────▼────┐         ┌────▼────┐        ┌────▼────┐
    │ Server  │         │ Server  │        │ Server  │
    │  AZ-A   │         │  AZ-B   │        │  AZ-C   │
    │         │         │         │        │         │
    │ Workers │         │ Workers │        │ Workers │
    │ 3-5x    │         │ 3-5x    │        │ 3-5x    │
    └─────────┘         └─────────┘        └─────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                    ┌────────▼─────────┐
                    │  Shared Services │
                    │  - Redis Cluster │
                    │  - RDS Postgres  │
                    │  - Prometheus    │
                    └──────────────────┘
```

---

## ⏱️ Timeout Budget

### Request Flow Timeouts

```
Client Request → Nginx → Worker → [Redis + Model + Postgres] → Response

Total: 30s
├─ Nginx timeout: 30s
├─ Worker request timeout: 30s
│  ├─ Model inference: 10s max
│  ├─ Redis operations: 2s each
│  │  ├─ Idempotency check: 2s
│  │  ├─ Cache get: 2s
│  │  └─ Cache set: 2s
│  └─ Postgres log: 5s (async, non-blocking)
```

### Recommended Timeout Configuration

| Component | Timeout | Rationale |
|-----------|---------|-----------|
| Nginx → Worker | 30s | Max request duration |
| Worker request | 30s | Overall request limit |
| Model inference | 10s | Should be <100ms typically |
| Redis operation | 2s | Should be <10ms typically |
| Postgres log | 5s | Non-blocking, can buffer |
| Retry delay | 100ms-5s | Exponential backoff |

**Cascade Considerations:**
- Set upstream timeouts < downstream timeouts
- Leave buffer for retries (retry budget)
- Monitor timeout occurrences as SLO violation

---

## 🔢 Resource Planning Worksheet

### Step 1: Estimate Traffic

**Questions:**
- Peak requests per second (RPS)?
- Average requests per second?
- Traffic pattern (steady, spiky, daily peaks)?
- Expected cache hit rate?

**Example:**
```
Peak RPS: 500
Average RPS: 200
Pattern: Daily peaks (9am-5pm)
Cache hit rate: 70%
```

### Step 2: Calculate Effective Load

```
Effective RPS = Peak RPS × (1 - cache_hit_rate)
              = 500 × (1 - 0.70)
              = 150 RPS (uncached)

Cached RPS = 500 × 0.70
           = 350 RPS (cached)
```

### Step 3: Calculate Workers Needed

```
Workers needed (uncached load) = Effective RPS / RPS_per_worker
                               = 150 / 60
                               = 2.5 → 3 workers

Workers needed (cached load) = Cached RPS / Cached_RPS_per_worker
                             = 350 / 250
                             = 1.4 → 2 workers

Total workers = max(3, 2) = 3 workers
With safety margin (60%): 3 / 0.6 = 5 workers
```

### Step 4: Calculate Resources

```
CPU = workers × 1.0 core = 5 × 1.0 = 5 cores
Memory = workers × 400 MB = 5 × 400 MB = 2 GB

Plus infrastructure:
Total CPU ≈ 5 + 1.5 = 6.5 cores → 8 vCPU
Total Memory ≈ 2 + 2 = 4 GB → 8 GB (with headroom)
```

### Step 5: Consider Growth

```
Growth factor (12 months): 2x
Future workers needed: 5 × 2 = 10 workers
Future CPU: 10 cores → 12-16 vCPU
Future Memory: 4 GB × 2 = 8 GB → 16 GB
```

---

## 💰 Cost Estimation

### AWS Example (us-east-1)

**Development Environment:**
- 1× t3.medium (2 vCPU, 4 GB) = $30/month
- 50 GB EBS gp3 = $4/month
- **Total**: ~$34/month

**Production Environment:**
- 1× c5.2xlarge (8 vCPU, 16 GB) = $250/month
- 100 GB EBS gp3 = $8/month
- ALB = $20/month
- **Total**: ~$278/month (single server)

**High-Availability Production:**
- 3× c5.xlarge (4 vCPU, 8 GB) = $375/month
- ALB = $20/month
- RDS Postgres t3.medium = $50/month
- ElastiCache Redis t3.small = $25/month
- **Total**: ~$470/month

### GCP Example (us-central1)

**Production:**
- 3× n2-standard-4 (4 vCPU, 16 GB) = $360/month
- Cloud Load Balancing = $20/month
- Cloud SQL Postgres db-n1-standard-1 = $80/month
- Memorystore Redis 5 GB = $30/month
- **Total**: ~$490/month

---

## 📊 Monitoring & Alerting

### Key Capacity Metrics

**Must Monitor:**
1. **RPS** - Track current vs. capacity
2. **CPU Utilization** - Alert at >80%
3. **Memory Usage** - Alert at >85%
4. **Latency p95/p99** - Track SLO violations
5. **Error Rate** - Should be <0.1%
6. **Cache Hit Rate** - Impacts capacity significantly
7. **Queue Depth** - If using queues
8. **Connection Pools** - Redis, Postgres utilization

**Capacity Alerts:**
```yaml
# Prometheus alert rules
- alert: ApproachingCapacity
  expr: sum(rate(inference_requests_total[5m])) > 0.8 * capacity_max_rps
  for: 10m
  annotations:
    summary: "Traffic approaching 80% of capacity"
    action: "Consider scaling up"

- alert: HighCPUUtilization
  expr: avg(cpu_usage_percent) > 80
  for: 15m
  annotations:
    summary: "CPU utilization sustained above 80%"
    action: "Scale vertically or horizontally"
```

---

## 🎯 Bottleneck Analysis

### Typical Bottlenecks (in order)

1. **Model Inference** (CPU-bound)
   - **Solution**: Scale workers, optimize model, use batch inference
   
2. **Database Writes** (I/O-bound)
   - **Solution**: Use async logging, buffer, batch inserts
   
3. **Redis** (Memory-bound)
   - **Solution**: Increase Redis memory, implement eviction policy
   
4. **Network Bandwidth** (Rare)
   - **Solution**: Compression, CDN, regional deployment

### How to Identify Current Bottleneck

```bash
# Run load test
k6 run tests/load/stress.js

# Check worker CPU
docker stats

# Check inference time
curl http://localhost/metrics | grep inference_duration

# Check DB latency
curl http://localhost/metrics | grep db_operation_duration

# Check Redis performance
docker exec falcon-redis redis-cli --latency
```

**Interpretation:**
- CPU >90%: Need more workers
- Inference time >500ms: Model optimization or batching
- DB latency >100ms: Database tuning or scaling
- Redis latency >10ms: Redis scaling or optimization

---

## 🔄 Scaling Checklist

### Before Scaling Up

- [ ] Confirm sustained high load (not temporary spike)
- [ ] Check current resource utilization
- [ ] Review recent changes (might be regression)
- [ ] Verify not hitting external limits (DB connections, etc.)
- [ ] Check cache hit rate (low rate = more load)
- [ ] Review logs for errors causing retries

### Scaling Up

- [ ] Update configuration (docker-compose.yml or K8s)
- [ ] Apply changes (docker compose up -d --scale)
- [ ] Verify new workers are healthy
- [ ] Check load distribution in Nginx
- [ ] Monitor metrics for 15 minutes
- [ ] Run load test to verify capacity
- [ ] Update capacity documentation
- [ ] Update monitoring alert thresholds

### After Scaling

- [ ] Document why scaling was needed
- [ ] Update capacity plan with new baseline
- [ ] Review cost impact
- [ ] Set new alerting thresholds
- [ ] Plan next scaling threshold

---

## 📚 References

- Load Testing Results: `tests/load/results/`
- Grafana Dashboard: http://localhost:3000
- Prometheus Metrics: http://localhost:9090

---

**Last Updated**: 2026-02-12  
**Next Review**: 2026-05-12  
**Owner**: SRE Team
