# Design Tradeoffs - Falcon ML Inference Platform

## 🎯 Overview

This document explains the key design decisions, their rationales, and the tradeoffs involved in building the Falcon ML Inference Platform.

---

## 1. Technology Stack Choices

### FastAPI vs Flask vs Django

**Choice**: FastAPI

**Rationale:**
- Native async support (better for I/O-bound operations)
- Automatic OpenAPI documentation
- Built-in request validation (Pydantic)
- High performance (comparable to Go/Node.js)
- Modern Python features (type hints)

**Tradeoffs:**
| Pros | Cons |
|------|------|
| ✅ Excellent performance | ❌ Smaller ecosystem vs Flask |
| ✅ Type safety with Pydantic | ❌ Steeper learning curve |
| ✅ Async/await built-in | ❌ Relatively newer (less mature) |
| ✅ Great for APIs | ❌ Not ideal for monolithic apps |

**Alternatives Considered:**
- **Flask**: Simpler, but no async and manual validation
- **Django**: Too heavy for API-only service
- **Go**: Better performance but longer development time

**At Meta Scale:**
- Would likely use **Thrift/gRPC** for internal services
- Consider **C++** for ultra-low latency requirements
- Use **Hack/PHP** if integrating with web platform

---

## 2. Nginx vs HAProxy vs Envoy

**Choice**: Nginx

**Rationale:**
- Battle-tested and mature
- Excellent performance for HTTP
- Simple configuration
- Built-in rate limiting
- Wide deployment experience

**Tradeoffs:**
| Pros | Cons |
|------|------|
| ✅ Mature and stable | ❌ Configuration can be complex |
| ✅ High performance | ❌ Limited observability vs Envoy |
| ✅ Extensive documentation | ❌ Reload needed for config changes |
| ✅ Built-in rate limiting | ❌ No dynamic service discovery |

**Alternatives Considered:**
- **HAProxy**: Slightly better for TCP, but less HTTP features
- **Envoy**: Better observability and service mesh integration, but more complex
- **Traefik**: Good for containers, but less mature for production

**At Meta Scale:**
- Would use **L4 load balancers** (Katran, IPVS)
- Service mesh (**Envoy**) for microservices
- **Proxygen** for internal HTTP proxying

---

## 3. Redis vs Memcached vs In-Memory

**Choice**: Redis

**Rationale:**
- Rich data structures (strings, hashes, sets)
- Persistence options (AOF, RDB)
- Pub/sub for future features
- Widely supported and documented

**Tradeoffs:**
| Pros | Cons |
|------|------|
| ✅ Rich features | ❌ Single-threaded (can bottleneck) |
| ✅ Persistence | ❌ Higher memory usage vs Memcached |
| ✅ Atomic operations | ❌ Need cluster for HA |
| ✅ TTL support | ❌ More complex than simple cache |

**Alternatives Considered:**
- **Memcached**: Simpler, slightly faster for simple KV, but no persistence
- **In-Memory Dict**: No network overhead, but no sharing between workers
- **Hazelcast**: More features, but Java-based and heavier

**At Meta Scale:**
- Would use **TAO** (Meta's distributed cache)
- Or **Mcrouter** (Memcached proxy) for routing
- **RocksDB** for persistent caching

---

## 4. PostgreSQL vs MySQL vs NoSQL

**Choice**: PostgreSQL

**Rationale:**
- ACID compliance for audit logs
- JSON support (probabilities field)
- Excellent query optimizer
- Strong consistency guarantees

**Tradeoffs:**
| Pros | Cons |
|------|------|
| ✅ ACID compliance | ❌ More resource-intensive vs MySQL |
| ✅ JSON support | ❌ Harder to scale horizontally |
| ✅ Advanced features | ❌ Complex replication setup |
| ✅ Strong consistency | ❌ Can be overkill for simple logs |

**Alternatives Considered:**
- **MySQL**: Slightly faster for simple queries, but weaker JSON support
- **MongoDB**: Better for unstructured data, but eventual consistency risks
- **Cassandra**: Better horizontal scaling, but eventual consistency
- **ClickHouse**: Better for analytics, but not OLTP

**At Meta Scale:**
- Would use **MyRocks** (RocksDB + MySQL)
- **Scribe** for log aggregation
- **Hive** for analytics queries
- **Sharding** across multiple databases

---

## 5. Synchronous vs Asynchronous Logging

**Choice**: Asynchronous with fallback buffer

**Rationale:**
- Don't block inference on DB writes
- Accept eventual consistency for logs
- Graceful degradation when DB slow/down

**Tradeoffs:**
| Pros | Cons |
|------|------|
| ✅ Doesn't block inference | ❌ Logs can be lost on crash |
| ✅ Better latency | ❌ Eventual consistency |
| ✅ Fallback to buffer | ❌ More complex code |
| ✅ Graceful degradation | ❌ Memory usage for buffer |

**Alternatives Considered:**
- **Synchronous**: Guaranteed logs, but blocks request and increases latency
- **Message Queue (Kafka)**: More reliable, but adds infrastructure complexity
- **Log to file only**: Simpler, but harder to query and analyze

**At Meta Scale:**
- Use **Scribe** (Meta's log aggregation)
- Write to local disk, async ship to central store
- **Eventually consistent** is acceptable for logs

---

## 6. Model Serving Architecture

### Embedded Model vs Separate Service

**Choice**: Embedded in worker process

**Rationale:**
- Lower latency (no network hop)
- Simpler deployment
- Better for small models
- Easier to scale (just add workers)

**Tradeoffs:**
| Pros | Cons |
|------|------|
| ✅ Low latency | ❌ Memory duplication per worker |
| ✅ Simple architecture | ❌ Worker restart needed for model update |
| ✅ No model service to manage | ❌ Not ideal for large models (>1GB) |
| ✅ Easy to scale | ❌ Coupling of model and API |

**Alternatives Considered:**
- **Separate Model Service** (TensorFlow Serving, TorchServe):
  - Better for large models
  - Independent scaling
  - But adds network latency and complexity
  
- **Batch Processing**:
  - Better throughput for high volume
  - But adds latency and complexity

**At Meta Scale:**
- Use **TorchServe** or custom model servers
- **Model sharding** for large models
- **GPU pools** for complex models
- **Batch inference** for non-realtime

### Batch Inference vs Real-time

**Choice**: Real-time with optional batching

**Rationale:**
- User-facing API needs low latency
- Small model is fast enough (<100ms)
- Batching optional for optimization

**Tradeoffs:**
| Batch | Real-time |
|-------|-----------|
| ✅ Higher throughput | ✅ Lower latency |
| ✅ Better GPU utilization | ✅ Simpler code |
| ❌ Higher latency | ❌ Lower throughput |
| ❌ More complex | ❌ Potential GPU underutilization |

**When to use Batch:**
- Large models with high inference cost
- GPU-based models
- High volume, latency-tolerant workloads

---

## 7. Circuit Breaker vs Retry Only

**Choice**: Both (Circuit Breaker + Retry)

**Rationale:**
- Retry handles transient failures
- Circuit breaker prevents cascade failures
- Together provide robust failure handling

**Tradeoffs:**
| Pros | Cons |
|------|------|
| ✅ Prevents cascade failures | ❌ More complex logic |
| ✅ Faster failure detection | ❌ Requires tuning thresholds |
| ✅ Auto-recovery | ❌ Can mask underlying issues |
| ✅ Better SLO adherence | ❌ Need good monitoring |

**Alternatives Considered:**
- **Retry only**: Simpler, but can cause retry storms
- **Timeout only**: Fastest failure, but no recovery logic
- **No resilience**: Simplest, but fragile

**At Meta Scale:**
- Use sophisticated circuit breakers (Resilience4j, Hystrix-like)
- **Bulkheads** to isolate failures
- **Adaptive timeouts** based on p99 latency
- **Chaos engineering** to test resilience

---

## 8. Monorepo vs Microservices

**Choice**: Monolith with modular structure

**Rationale:**
- Single service simplifies ops
- Inference is coherent bounded context
- Avoid distributed system complexity
- Easy to develop and deploy

**Tradeoffs:**
| Monolith | Microservices |
|----------|---------------|
| ✅ Simple deployment | ❌ Harder to scale independently |
| ✅ No network overhead | ❌ All-or-nothing scaling |
| ✅ Easier to develop | ❌ Shared fate (one bug affects all) |
| ✅ Better performance | ❌ Can become complex |
| ❌ Hard to split later | ✅ Independent scaling |
| ❌ Single tech stack | ✅ Technology flexibility |

**When to Split:**
- Different scaling needs (model vs API)
- Different teams owning components
- Different SLOs
- Different deployment cadences

**At Meta Scale:**
- Would be **microservices** with service mesh
- Separate services for: API, model serving, feature computation
- **gRPC** for inter-service communication

---

## 9. Docker Compose vs Kubernetes

**Choice**: Docker Compose for demo, Kubernetes for production

**Rationale:**
- Docker Compose is simple for single-server
- Kubernetes needed for multi-server HA
- K8s overkill for development

**Tradeoffs:**
| Docker Compose | Kubernetes |
|----------------|------------|
| ✅ Simple setup | ❌ Complex |
| ✅ Good for dev/demo | ❌ Steep learning curve |
| ✅ Fast iteration | ❌ Slower to set up |
| ❌ No HA | ✅ High availability |
| ❌ Single server | ✅ Multi-server |
| ❌ Manual scaling | ✅ Auto-scaling |

**Migration Path:**
```
Development → Single Server (Docker Compose) → 
Production → Kubernetes (or ECS/EKS)
```

**At Meta Scale:**
- Use **Tupperware** (Meta's container orchestration)
- Or **Kubernetes** with custom controllers
- **Service mesh** (Istio/Linkerd) for traffic management

---

## 10. Observability Stack

### Prometheus vs DataDog vs CloudWatch

**Choice**: Prometheus + Grafana

**Rationale:**
- Open source and self-hosted
- Industry standard for metrics
- Powerful query language (PromQL)
- Free (no per-metric costs)

**Tradeoffs:**
| Self-hosted (Prometheus) | SaaS (DataDog) |
|--------------------------|----------------|
| ✅ Free | ❌ Requires ops |
| ✅ Full control | ❌ Need to scale/maintain |
| ✅ No vendor lock-in | ✅ Zero ops |
| ❌ Need to manage | ✅ Rich features |
| ❌ Manual scaling | ✅ Auto-scaling |
| ❌ Self-service setup | ✅ APM, logs, metrics unified |

**When to use SaaS:**
- Small team with no SRE
- Want to move fast
- Budget available
- Need APM/distributed tracing

**At Meta Scale:**
- Custom metrics infrastructure (**ODS** - Operational Data Store)
- **Scuba** for exploratory analytics
- **Unbreak** for incident management

---

## 🎓 Key Takeaways

### Good Tradeoffs Made

1. **Async logging** - Improved latency at cost of complexity
2. **Circuit breakers** - Resilience at cost of code complexity
3. **Embedded model** - Simplicity for small model use case
4. **Monolith architecture** - Right size for single bounded context

### Areas for Future Improvement

1. **Authentication** - Currently missing, needed for production
2. **Distributed tracing** - Would help debug latency issues
3. **Model versioning** - Need A/B testing and rollback
4. **Multi-region** - For global low latency

### Lessons for Meta-Scale Systems

- Start simple, add complexity when needed
- Measure before optimizing
- Build for observability from day 1
- Design for failure (circuit breakers, retries)
- Separate control plane from data plane
- Cache aggressively but with invalidation strategy

---

**Last Updated**: 2026-02-12  
**Next Review**: When requirements change  
**Owner**: Architecture Team
