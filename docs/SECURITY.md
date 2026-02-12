# Security Considerations - Falcon ML Inference Platform

## 🔒 Overview

This document outlines the security considerations, threat model, and mitigation strategies for the Falcon ML Inference Platform.

**Security Posture**: Defense in depth with multiple layers of protection.

---

## 🎯 Threat Model

### Assets

1. **ML Model** - Proprietary intellectual property
2. **User Data** - Inference requests (potentially sensitive)
3. **Infrastructure** - Servers, containers, credentials
4. **Logs** - May contain PII or business-sensitive data
5. **Metrics** - System performance data

### Threat Actors

1. **External Attackers** - Attempting unauthorized access
2. **Malicious Users** - Abusing the API
3. **Insider Threats** - Compromised credentials
4. **Supply Chain** - Compromised dependencies

### Attack Vectors

1. **API Abuse** - DDoS, resource exhaustion
2. **Injection Attacks** - SQL injection, command injection
3. **Data Exfiltration** - Stealing models or data
4. **Credential Compromise** - Stolen secrets
5. **Container Escape** - Breaking out of containerization

---

## 🛡️ Security Controls

### 1. Input Validation

**Current Implementation:**

```python
# app/models/schemas.py
class InferenceRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        max_length=10000,  # Prevent extremely large inputs
    )
    
    @validator("text")
    def validate_text(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Text cannot be empty")
        return v
```

**Protection Against:**
- Oversized payloads
- Empty/malformed requests
- Type confusion attacks

**Recommendations:**
```python
# Additional validation
- Sanitize HTML/script tags if user input is displayed
- Validate encoding (UTF-8 only)
- Check for null bytes
- Rate limit by content hash to prevent abuse
```

### 2. Rate Limiting

**Current Implementation:**

```nginx
# nginx/conf.d/falcon.conf
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/s;
limit_req zone=api_limit burst=20 nodelay;
limit_conn_zone $binary_remote_addr zone=conn_limit:10m;
limit_conn conn_limit 10;
```

**Protection Against:**
- DDoS attacks
- Resource exhaustion
- Brute force attempts

**Recommendations:**
```
Production Configuration:
- Implement token bucket algorithm
- Use API keys with per-key limits
- Implement exponential backoff for repeated violators
- Add CAPTCHA for suspicious patterns
- Monitor rate_limit_exceeded metric
```

### 3. Authentication & Authorization

**Current State:**
- ⚠️ **No authentication in demo** (intended for internal network)

**Production Requirements:**

```python
# Add to app/api/routes.py
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

@router.post("/infer")
async def infer(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    # Validate JWT token
    token = credentials.credentials
    user = validate_jwt(token)
    # ... rest of inference logic
```

**Options:**
1. **API Keys** - Simple, for service-to-service
2. **JWT Tokens** - For user authentication
3. **mTLS** - For strong service authentication
4. **OAuth 2.0** - For third-party integration

### 4. Secrets Management

**Current State:**
```bash
# .env file (NOT FOR PRODUCTION)
POSTGRES_PASSWORD=falcon_dev_password_change_in_prod
```

**Production Requirements:**

**DO:**
✅ Use secret management service:
- AWS Secrets Manager
- Google Secret Manager
- HashiCorp Vault
- Kubernetes Secrets (with encryption at rest)

✅ Rotate secrets regularly:
- Database passwords: 90 days
- API keys: 90 days
- Certificates: Before expiry

✅ Principle of least privilege:
- Workers: Read-only model access
- No root in containers
- Separate credentials per service

**DON'T:**
❌ Commit secrets to git
❌ Log secrets
❌ Store secrets in environment variables (use secret store)
❌ Hardcode secrets in code

**Implementation:**

```python
# Use secret manager
import boto3

def get_secret(secret_name):
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])

# In config.py
if settings.environment == "production":
    secrets = get_secret("falcon/prod/database")
    settings.postgres_password = secrets['password']
```

### 5. Network Security

**Current Implementation:**

```yaml
# docker-compose.yml
networks:
  falcon-network:
    driver: bridge  # Isolated network
```

**Production Requirements:**

```
┌──────────────────────────────────────┐
│          Public Internet             │
└────────────┬─────────────────────────┘
             │
      ┌──────▼──────┐
      │   Firewall  │  ← Only ports 80, 443
      │   (UFW/SG)  │
      └──────┬──────┘
             │
      ┌──────▼──────┐
      │  DMZ Zone   │
      │  - Nginx    │  ← Reverse proxy only
      └──────┬──────┘
             │
      ┌──────▼──────────┐
      │ Application Zone │
      │ - Workers       │  ← No direct internet access
      └──────┬──────────┘
             │
      ┌──────▼──────────┐
      │  Data Zone      │
      │ - Redis         │  ← Strict ACLs
      │ - Postgres      │
      └─────────────────┘
```

**Firewall Rules:**
```bash
# UFW example
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 22/tcp    # SSH (restrict to bastion)
sudo ufw enable
```

**AWS Security Groups:**
```terraform
# ALB Security Group
ingress {
  from_port   = 80
  to_port     = 80
  protocol    = "tcp"
  cidr_blocks = ["0.0.0.0/0"]
}

# Worker Security Group
ingress {
  from_port       = 8000
  to_port         = 8000
  protocol        = "tcp"
  security_groups = [aws_security_group.alb.id]
}

# Database Security Group
ingress {
  from_port       = 5432
  to_port         = 5432
  protocol        = "tcp"
  security_groups = [aws_security_group.workers.id]
}
```

### 6. Data Protection

#### Data in Transit

**Current:**
```nginx
# HTTP only (demo)
listen 80;
```

**Production:**
```nginx
# HTTPS with TLS 1.3
server {
    listen 443 ssl http2;
    ssl_protocols TLSv1.3 TLSv1.2;
    ssl_ciphers 'TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384';
    ssl_prefer_server_ciphers off;
    
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    
    # Redirect HTTP to HTTPS
    if ($scheme != "https") {
        return 301 https://$host$request_uri;
    }
}
```

#### Data at Rest

**Postgres:**
```bash
# Enable encryption
docker run -e POSTGRES_INITDB_ARGS="--data-checksums" \
           -e PGDATA=/var/lib/postgresql/data/pgdata \
           -v /encrypted/volume:/var/lib/postgresql/data \
           postgres:15
```

**Redis:**
```bash
# Use encrypted EBS/disk
# Redis doesn't encrypt at rest natively, rely on volume encryption
```

**Logs:**
```python
# Redact sensitive data
import re

def redact_pii(log_message):
    # Email addresses
    log_message = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 
                         '[REDACTED_EMAIL]', log_message)
    # Credit cards
    log_message = re.sub(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',
                         '[REDACTED_CC]', log_message)
    return log_message
```

### 7. Container Security

**Current Best Practices:**

```dockerfile
# Dockerfile
FROM python:3.11-slim  # Minimal base image

# Don't run as root
RUN groupadd -r falcon && useradd -r -g falcon falcon

# ... install dependencies ...

USER falcon  # Switch to non-root user

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1
```

**Additional Recommendations:**

```dockerfile
# Multi-stage build to reduce attack surface
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.11-slim
COPY --from=builder /root/.local /root/.local
COPY app/ /app/
USER 1000:1000  # Numeric UID (more portable)
```

**Security Scanning:**
```bash
# Scan for vulnerabilities
docker scan falcon-worker:latest

# Trivy
trivy image falcon-worker:latest

# Anchore
anchore-cli image add falcon-worker:latest
anchore-cli image vuln falcon-worker:latest all
```

**Runtime Security:**
```bash
# Read-only root filesystem
docker run --read-only falcon-worker

# Drop capabilities
docker run --cap-drop=ALL --cap-add=NET_BIND_SERVICE falcon-worker

# Security profiles
docker run --security-opt=no-new-privileges:true falcon-worker
```

### 8. Logging & Monitoring

**Security Logging:**

```python
# Log security events
logger.warning(
    "Rate limit exceeded",
    extra={
        "client_ip": client_ip,
        "endpoint": "/infer",
        "request_count": count,
        "security_event": "rate_limit",
    }
)

logger.error(
    "Invalid authentication token",
    extra={
        "client_ip": client_ip,
        "security_event": "auth_failure",
    }
)
```

**Security Metrics:**

```python
from prometheus_client import Counter

auth_failures = Counter(
    "auth_failures_total",
    "Total authentication failures",
    ["reason"]
)

rate_limit_exceeded = Counter(
    "rate_limit_exceeded_total",
    "Rate limit exceeded events",
    ["endpoint"]
)
```

**Alerts:**

```yaml
# prometheus/alerts/security_alerts.yml
- alert: HighAuthFailureRate
  expr: rate(auth_failures_total[5m]) > 10
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "High authentication failure rate detected"

- alert: RateLimitAbuse
  expr: rate(rate_limit_exceeded_total[5m]) > 50
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Potential API abuse detected"
```

### 9. Dependency Management

**Current:**
```bash
# requirements.txt with pinned versions
fastapi==0.109.0
uvicorn==0.27.0
```

**Security Practices:**

```bash
# Check for vulnerabilities
pip-audit

# Or use safety
safety check -r requirements.txt

# Update dependencies regularly
pip list --outdated
```

**Automated Scanning:**
```yaml
# .github/workflows/security.yml
- name: Run pip-audit
  run: |
    pip install pip-audit
    pip-audit -r requirements.txt
```

**Supply Chain Security:**
```bash
# Verify package hashes
pip install --require-hashes -r requirements.txt

# Use private PyPI mirror
pip install --index-url https://private-pypi.company.com/simple
```

### 10. Incident Response

**Security Incident Playbook:**

1. **Detection**
   - Monitor security alerts
   - Review logs for anomalies
   - User reports

2. **Containment**
   ```bash
   # Isolate affected container
   docker network disconnect falcon-network falcon-worker-1
   
   # Block malicious IP at firewall
   sudo ufw deny from <ip_address>
   
   # Rotate credentials if compromised
   ```

3. **Investigation**
   ```bash
   # Collect logs
   docker logs falcon-worker-1 > incident-logs.json
   
   # Check database for unauthorized access
   SELECT * FROM inference_logs 
   WHERE created_at > 'incident-time'
   ORDER BY created_at;
   ```

4. **Recovery**
   - Patch vulnerabilities
   - Restore from clean backup
   - Rotate all credentials
   - Update firewall rules

5. **Post-Incident**
   - Write postmortem (see POSTMORTEM_TEMPLATE.md)
   - Update security controls
   - Add detection for similar incidents

---

## 🔍 Security Checklist

### Pre-Production

- [ ] Enable HTTPS/TLS with valid certificates
- [ ] Implement authentication (API keys/JWT)
- [ ] Move secrets to secret manager
- [ ] Enable firewall with minimal ports
- [ ] Set up network segmentation
- [ ] Enable database encryption at rest
- [ ] Configure security headers (CSP, HSTS, etc.)
- [ ] Set up security monitoring/alerts
- [ ] Scan containers for vulnerabilities
- [ ] Run SAST/DAST security scans
- [ ] Perform penetration testing
- [ ] Review and sign off security checklist

### Production Operations

- [ ] Monitor security alerts daily
- [ ] Review access logs weekly
- [ ] Update dependencies monthly
- [ ] Rotate credentials quarterly
- [ ] Conduct security audits quarterly
- [ ] Test incident response annually
- [ ] Review and update security docs

---

## 🔧 Security Headers

**Add to Nginx:**

```nginx
# Security headers
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

# Remove version disclosure
server_tokens off;
```

---

## 📚 Security Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)

---

**Last Updated**: 2026-02-12  
**Next Review**: 2026-05-12  
**Owner**: Security Team
