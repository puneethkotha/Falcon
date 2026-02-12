# Ubuntu 22.04 Deployment Guide

## 🎯 Overview

This guide walks through deploying the Falcon ML Inference Platform on Ubuntu 22.04 LTS, suitable for AWS EC2, Google Cloud, Azure, or bare metal servers.

---

## 📋 Prerequisites

- Ubuntu 22.04 LTS server
- Minimum: 4 vCPU, 8 GB RAM, 50 GB disk
- Recommended: 8 vCPU, 16 GB RAM, 100 GB disk
- sudo/root access
- Open ports: 80, 443, 22 (SSH)

---

## 🚀 Step 1: Initial Server Setup

### Update System

```bash
sudo apt update && sudo apt upgrade -y
sudo reboot  # If kernel updates were installed
```

### Create Application User

```bash
# Create falcon user
sudo useradd -m -s /bin/bash falcon

# Add to docker group (will create later)
sudo usermod -aG sudo falcon  # Only if needed for deployment

# Switch to falcon user
sudo su - falcon
```

---

## 🐳 Step 2: Install Docker

### Install Docker Engine

```bash
# Install prerequisites
sudo apt install -y ca-certificates curl gnupg lsb-release

# Add Docker's official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

### Configure Docker

```bash
# Add user to docker group
sudo usermod -aG docker falcon
newgrp docker  # Or logout/login

# Enable Docker service
sudo systemctl enable docker
sudo systemctl start docker

# Verify Docker is working
docker run hello-world
```

---

## 🔥 Step 3: Configure Firewall

### Using UFW (Ubuntu Firewall)

```bash
# Install UFW
sudo apt install -y ufw

# Set default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (IMPORTANT: Do this first!)
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow Grafana (optional, for external access)
sudo ufw allow 3000/tcp

# Allow Prometheus (optional, for external access)
sudo ufw allow 9090/tcp

# Enable firewall
sudo ufw enable

# Verify
sudo ufw status verbose
```

### AWS Security Group (if using EC2)

Add inbound rules:
- Type: HTTP, Port: 80, Source: 0.0.0.0/0
- Type: HTTPS, Port: 443, Source: 0.0.0.0/0
- Type: Custom TCP, Port: 3000, Source: Your IP (Grafana)
- Type: Custom TCP, Port: 9090, Source: Your IP (Prometheus)
- Type: SSH, Port: 22, Source: Your IP

---

## 📦 Step 4: Deploy Application

### Clone Repository

```bash
# Create application directory
sudo mkdir -p /opt/falcon
sudo chown falcon:falcon /opt/falcon
cd /opt/falcon

# Clone repository
git clone https://github.com/puneethkotha/Falcon.git .

# Or download release
# wget https://github.com/puneethkotha/Falcon/archive/refs/tags/v1.0.0.tar.gz
# tar -xzf v1.0.0.tar.gz --strip-components=1
```

### Configure Environment

```bash
# Copy example environment
cp .env.example .env

# Edit configuration
nano .env

# Update these values:
# - Change all passwords
# - Set ENVIRONMENT=production
# - Update any host-specific settings
```

**Important Production Settings:**

```bash
# .env
ENVIRONMENT=production
LOG_LEVEL=INFO
DEBUG_MEMORY_GROWTH=false  # MUST be false!

# Change passwords
POSTGRES_PASSWORD=<strong-password-here>
GRAFANA_ADMIN_PASSWORD=<strong-password-here>

# Adjust resources based on server
POSTGRES_POOL_SIZE=20
REDIS_MAX_CONNECTIONS=50
```

### Train Model

```bash
# Install Python locally (for training script)
sudo apt install -y python3.11 python3-pip

# Train model
python3 scripts/train_model.py

# Verify model exists
ls -lh models/classifier.pkl
```

---

## 🎬 Step 5: Start Services

### Using Docker Compose

```bash
# Build and start services
docker compose up -d

# View logs
docker compose logs -f

# Wait for healthy (about 30 seconds)
sleep 30

# Check health
curl http://localhost/healthz
```

### Verify All Services

```bash
# Check running containers
docker ps

# Should see:
# - falcon-nginx
# - falcon-worker-1, falcon-worker-2, falcon-worker-3
# - falcon-redis
# - falcon-postgres
# - falcon-prometheus
# - falcon-grafana
# - falcon-cadvisor

# Test inference
curl -X POST http://localhost/infer \
  -H "Content-Type: application/json" \
  -d '{"text": "This is a great product!"}'

# Access dashboards
# Grafana: http://<server-ip>:3000 (admin/admin_change_in_prod)
# Prometheus: http://<server-ip>:9090
```

---

## 🔧 Step 6: Set Up Systemd Service

### Install Service File

```bash
# Copy systemd service
sudo cp deploy/systemd/falcon-inference.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable falcon-inference

# Start service
sudo systemctl start falcon-inference

# Check status
sudo systemctl status falcon-inference
```

### Manage Service

```bash
# Start
sudo systemctl start falcon-inference

# Stop
sudo systemctl stop falcon-inference

# Restart
sudo systemctl restart falcon-inference

# View logs
sudo journalctl -u falcon-inference -f

# View recent logs
sudo journalctl -u falcon-inference --since "1 hour ago"
```

---

## 🔍 Step 7: Monitoring & Verification

### Check System Resources

```bash
# CPU and memory
top
htop  # If installed: sudo apt install htop

# Disk usage
df -h

# Network connections
ss -tlnp | grep -E '(80|3000|5432|6379|9090)'

# Docker stats
docker stats
```

### Check Application Health

```bash
# Health endpoint
curl http://localhost/healthz

# Readiness (includes dependencies)
curl http://localhost/readyz

# Metrics
curl http://localhost/metrics | head -50

# Test inference with idempotency
curl -X POST http://localhost/infer \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: test-123" \
  -d '{"text": "Amazing service!"}'

# Run again (should be idempotent)
curl -X POST http://localhost/infer \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: test-123" \
  -d '{"text": "Amazing service!"}'
```

### View Logs

```bash
# Application logs (structured JSON)
docker compose logs worker-1 | jq

# Filter for errors
docker compose logs worker-1 | jq 'select(.level=="ERROR")'

# Nginx access logs
docker compose logs nginx

# Database logs
docker compose logs postgres
```

---

## 🚨 Step 8: Set Up HTTPS (Optional but Recommended)

### Using Let's Encrypt with Certbot

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Stop nginx container temporarily
docker compose stop nginx

# Get certificate
sudo certbot certonly --standalone -d your-domain.com

# Certificates will be in:
# /etc/letsencrypt/live/your-domain.com/

# Update nginx configuration
# Edit nginx/conf.d/falcon.conf to add SSL configuration

# Restart nginx
docker compose start nginx

# Set up auto-renewal
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

**Nginx SSL Configuration:**

Add to `nginx/conf.d/falcon.conf`:

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # ... rest of configuration ...
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

---

## 📊 Step 9: Configure Monitoring

### Access Grafana

1. Open browser: `http://<server-ip>:3000`
2. Login: `admin / admin_change_in_prod`
3. Change password immediately
4. Dashboard is pre-configured at: "Falcon ML Inference Platform"

### Set Up Alerts (Optional)

```bash
# If using external alerting (PagerDuty, Slack, etc.)
# Configure in Grafana:
# 1. Go to Alerting > Notification channels
# 2. Add your notification method
# 3. Link to dashboard alerts
```

---

## 🔄 Step 10: Updates & Maintenance

### Update Application

```bash
cd /opt/falcon

# Pull latest code
git pull

# Rebuild containers
docker compose build

# Restart services
docker compose up -d

# Or use systemctl
sudo systemctl restart falcon-inference
```

### Backup

```bash
# Backup database
docker compose exec postgres pg_dump -U falcon falcon_inference > \
  backup_$(date +%Y%m%d_%H%M%S).sql

# Backup configuration
tar -czf config_backup.tar.gz .env nginx/ grafana/

# Backup model
cp models/classifier.pkl models/classifier.pkl.backup
```

### Log Rotation

```bash
# Docker handles log rotation, but you can configure:
sudo nano /etc/docker/daemon.json

# Add:
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}

# Restart Docker
sudo systemctl restart docker
```

---

## 🐛 Troubleshooting

### Services Won't Start

```bash
# Check Docker is running
sudo systemctl status docker

# Check disk space
df -h

# Check logs
docker compose logs

# Check port conflicts
ss -tlnp | grep -E '(80|3000|5432|6379)'
```

### High Memory Usage

```bash
# Check container stats
docker stats

# Restart high-memory containers
docker compose restart worker-1

# Check for memory leaks
docker compose logs worker-1 | grep -i memory
```

### Network Issues

```bash
# Check firewall
sudo ufw status

# Check listening ports
ss -tlnp

# Test connectivity
curl -v http://localhost/healthz

# Check DNS
nslookup your-domain.com
```

### Database Issues

```bash
# Check database
docker compose exec postgres pg_isready -U falcon

# Check connections
docker compose exec postgres psql -U falcon -d falcon_inference -c \
  "SELECT count(*) FROM pg_stat_activity;"

# Restart database
docker compose restart postgres
```

---

## 📚 Quick Reference

### Essential Commands

```bash
# Start services
sudo systemctl start falcon-inference

# Stop services
sudo systemctl stop falcon-inference

# View logs
sudo journalctl -u falcon-inference -f

# Health check
curl http://localhost/healthz

# Container stats
docker stats

# Restart specific worker
docker compose restart worker-1
```

### Important Locations

| Item | Location |
|------|----------|
| Application | /opt/falcon |
| Configuration | /opt/falcon/.env |
| Logs | journalctl or docker logs |
| Systemd service | /etc/systemd/system/falcon-inference.service |
| SSL certificates | /etc/letsencrypt/live/ |

---

## ✅ Deployment Checklist

- [ ] Server meets minimum requirements
- [ ] Docker installed and running
- [ ] Firewall configured
- [ ] Repository cloned
- [ ] Environment configured (.env)
- [ ] Passwords changed from defaults
- [ ] Model trained
- [ ] Services started
- [ ] Health checks passing
- [ ] Systemd service enabled
- [ ] HTTPS configured (if applicable)
- [ ] Grafana accessible
- [ ] Monitoring configured
- [ ] Backup strategy in place
- [ ] Documentation reviewed

---

## 🆘 Support

- **Documentation**: [README.md](../README.md)
- **Runbook**: [docs/RUNBOOK.md](../docs/RUNBOOK.md)
- **Issues**: https://github.com/puneethkotha/Falcon/issues

---

**Last Updated**: 2026-02-12  
**Tested On**: Ubuntu 22.04 LTS, AWS EC2 t3.large
