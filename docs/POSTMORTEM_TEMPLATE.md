# Incident Postmortem Template

## Incident Details

| Field | Value |
|-------|-------|
| **Incident ID** | INC-YYYY-MM-DD-XXX |
| **Date/Time** | YYYY-MM-DD HH:MM UTC |
| **Duration** | X hours Y minutes |
| **Severity** | P0 / P1 / P2 / P3 |
| **Incident Commander** | Name |
| **Responders** | List of people |
| **Status** | RESOLVED / MITIGATED |

---

## Executive Summary

_1-2 paragraph summary of what happened, the impact, and the fix._

**Example:**
> On 2026-02-12 at 14:35 UTC, the Falcon ML Inference Platform experienced a complete outage lasting 47 minutes, affecting 100% of inference requests. The root cause was a memory leak introduced in the v2.3.1 deployment that caused all worker containers to crash. The issue was mitigated by rolling back to v2.3.0 and has been resolved with a hotfix in v2.3.2.

---

## Impact

### User Impact

| Metric | Value |
|--------|-------|
| **Users Affected** | X users / Y% of total |
| **Requests Affected** | X requests |
| **Error Rate** | X% |
| **Revenue Impact** | $X (if applicable) |
| **Duration** | X hours Y minutes |

### SLO Impact

| SLO | Target | Actual | Breach |
|-----|--------|--------|--------|
| **Availability** | 99.9% | 99.5% | YES |
| **p95 Latency** | <500ms | 2300ms | YES |
| **Error Rate** | <0.1% | 12.5% | YES |

---

## Timeline

_All times in UTC. Include key events, decisions, and actions._

| Time | Event | Action Taken |
|------|-------|--------------|
| 14:30 | Deployment started (v2.3.1) | Engineer triggered deployment |
| 14:35 | First alerts fire (High Error Rate) | On-call engineer paged |
| 14:37 | Worker-1 crashes (OOM) | Auto-restart triggered |
| 14:38 | Worker-2 crashes (OOM) | Auto-restart triggered |
| 14:39 | Worker-3 crashes (OOM) | Auto-restart triggered |
| 14:40 | All workers in crash loop | Incident declared |
| 14:42 | Incident Commander joins | IC takes over coordination |
| 14:45 | Recent deployment identified as suspect | IC orders rollback |
| 14:48 | Rollback initiated | Engineer executes rollback |
| 14:55 | Workers healthy after rollback | Services restored |
| 15:05 | Error rate back to normal | Monitoring continues |
| 15:22 | All clear given | Incident resolved |

### Key Decision Points

**14:42 - Should we rollback or debug?**
- **Decision**: Rollback immediately
- **Rationale**: User impact was 100%, debuggin would take too long
- **Result**: Correct decision, restored service quickly

---

## Root Cause Analysis

### What Happened

_Detailed technical explanation of the failure._

**Example:**
> The v2.3.1 deployment introduced a memory leak in the request processing code. Specifically, the new caching logic in `app/api/routes.py` was appending data to a global list `_debug_memory_ballast` that was never cleared. The `DEBUG_MEMORY_GROWTH` flag was accidentally set to `true` in the production .env file.
>
> This caused each request to allocate an additional 5MB of memory that was never freed. Under production load (~100 RPS), workers accumulated 500MB/minute, reaching the 1GB container limit in approximately 2 minutes after deployment.

### Why It Happened

**Immediate Cause:**
- `DEBUG_MEMORY_GROWTH=true` in production .env

**Contributing Factors:**
1. Debug flag was not caught in code review
2. No alerting on env var changes
3. Deployment didn't run load tests
4. Memory limits were not set in docker-compose.yml

**Root Cause:**
- Insufficient pre-production testing
- Debug code made it to production
- No safeguards against misconfigurations

### The 5 Whys

1. **Why did the service go down?**
   - Workers ran out of memory and crashed

2. **Why did workers run out of memory?**
   - Debug memory growth feature was enabled

3. **Why was the debug feature enabled?**
   - The .env file had DEBUG_MEMORY_GROWTH=true

4. **Why did this make it to production?**
   - The deployment process didn't validate environment variables

5. **Why wasn't it caught in testing?**
   - Load tests were not run before production deployment

---

## Detection & Response

### What Went Well

✅ Alerts fired within 5 minutes of issue  
✅ On-call engineer responded quickly  
✅ Incident Commander took charge  
✅ Team made correct decision to rollback  
✅ Rollback was successful  
✅ Communication was clear  

### What Went Poorly

❌ Issue not caught in code review  
❌ No pre-deployment validation  
❌ No load testing before prod  
❌ Memory limits not configured  
❌ Debug flag not clearly marked as dangerous  
❌ Took 10 minutes to identify cause  

---

## Resolution & Recovery

### Immediate Mitigation

```bash
# Rollback to previous version
git checkout v2.3.0
docker compose build
docker compose up -d

# Verify healthy
make check-health
```

### Permanent Fix

**Hotfix v2.3.2:**
```python
# app/api/routes.py
# Remove debug memory growth code entirely
# Changed from:
if settings.debug_memory_growth:
    _debug_memory_ballast.append(bytearray(...))

# To: Removed entirely (debug code should not be in production)
```

**Deployed**: 2026-02-12 16:30 UTC  
**Verification**: Load test passed, memory stable  

---

## Action Items

### Prevent

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Remove all debug flags from production code | @engineer | 2026-02-15 | DONE |
| Add pre-commit hook to check for debug flags | @engineer | 2026-02-16 | DONE |
| Add .env validation in deployment pipeline | @sre | 2026-02-20 | IN PROGRESS |
| Set memory limits in docker-compose.yml | @sre | 2026-02-14 | DONE |
| Create separate dev/prod .env templates | @engineer | 2026-02-17 | TODO |

### Detect

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Add alert for memory usage >80% | @sre | 2026-02-15 | DONE |
| Add alert for OOM kills | @sre | 2026-02-15 | DONE |
| Add deployment validation gate | @sre | 2026-02-22 | IN PROGRESS |
| Monitor env var changes | @sre | 2026-02-25 | TODO |

### Respond

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Update runbook with OOM scenario | @sre | 2026-02-16 | DONE |
| Add rollback command to runbook | @sre | 2026-02-16 | DONE |
| Practice rollback procedure | @team | 2026-03-01 | TODO |

### Long-term

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Implement load testing in CI/CD | @sre | 2026-03-15 | TODO |
| Add canary deployment | @sre | 2026-04-01 | TODO |
| Automated rollback on errors >10% | @sre | 2026-04-15 | TODO |

---

## Lessons Learned

### What We Learned

1. **Debug code is dangerous in production**
   - Should never make it to prod
   - Need automated checks

2. **Memory limits are essential**
   - Prevent OOM from taking down entire host
   - Should be set conservatively

3. **Load testing before deployment**
   - Would have caught this immediately
   - Need to automate in pipeline

4. **Rollback is fastest mitigation**
   - Correct decision in this case
   - Need to practice regularly

### Process Improvements

1. **Code Review Checklist**
   - Add item: "No debug flags or test code"
   - Require 2 reviewers for production changes

2. **Deployment Pipeline**
   - Add env validation step
   - Add automated load test
   - Add canary deployment

3. **Monitoring**
   - Add memory usage alerts
   - Add OOM kill alerts
   - Monitor env var changes

4. **Documentation**
   - Update runbook with this scenario
   - Document rollback procedures
   - Create deployment checklist

---

## Supporting Information

### Graphs & Dashboards

_Include screenshots or links to relevant graphs_

- **Error Rate**: [Grafana Link]
- **Memory Usage**: [Grafana Link]
- **Request Latency**: [Grafana Link]

### Logs

_Include relevant log snippets_

```json
{
  "timestamp": "2026-02-12T14:37:22Z",
  "level": "ERROR",
  "message": "Container OOMKilled",
  "worker_id": "worker-1",
  "exit_code": 137
}
```

### Related Incidents

- **INC-2025-11-05-012**: Similar OOM incident (different cause)
- **INC-2026-01-15-045**: Deployment rollback incident

---

## Communication

### Internal

- [x] Incident declared in #incidents channel
- [x] Status updates every 15 minutes
- [x] Postmortem shared with team
- [x] Lessons learned presented in team meeting

### External

- [x] Status page updated
- [x] Customer email sent (if applicable)
- [x] Support team notified

### Postmortem Review

- **Review Meeting**: 2026-02-14 10:00 UTC
- **Attendees**: SRE team, Engineering team, Management
- **Outcome**: Action items assigned and tracked

---

## Sign-off

| Role | Name | Date |
|------|------|------|
| **Author** | Engineer Name | 2026-02-13 |
| **Reviewed By** | SRE Lead | 2026-02-13 |
| **Approved By** | Engineering Manager | 2026-02-14 |

---

**Related Documents:**
- [Runbook](RUNBOOK.md)
- [Capacity Plan](CAPACITY_PLAN.md)
- [Architecture](../README.md)

---

_This template should be filled out within 48 hours of incident resolution._
