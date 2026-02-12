#!/bin/bash
set -e

echo "=================================================="
echo "Falcon ML Inference Platform - Deployment Script"
echo "=================================================="
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "⚠️  Please do not run as root. Run as the falcon user."
    exit 1
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    echo "   See: https://docs.docker.com/engine/install/"
    exit 1
fi

# Check if docker compose is available
if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose is not installed or not available."
    echo "   Please install Docker Compose V2."
    exit 1
fi

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from .env.example..."
    cp .env.example .env
    echo "✓ Created .env file"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env and change passwords before deploying to production!"
    echo ""
    read -p "Press Enter to continue or Ctrl+C to abort..."
fi

# Check if model exists
if [ ! -f models/classifier.pkl ]; then
    echo "⚠️  Model not found. Training model..."
    python3 scripts/train_model.py
    echo "✓ Model trained"
fi

echo "Step 1: Pulling latest images..."
docker compose pull

echo ""
echo "Step 2: Building application..."
docker compose build

echo ""
echo "Step 3: Starting services..."
docker compose up -d

echo ""
echo "Step 4: Waiting for services to be healthy..."
sleep 30

echo ""
echo "Step 5: Checking health..."
HEALTH_URL="http://localhost/healthz"

for i in {1..10}; do
    if curl -sf $HEALTH_URL > /dev/null; then
        echo "✓ Services are healthy!"
        break
    else
        echo "  Attempt $i/10: Services not ready yet..."
        sleep 5
    fi
    
    if [ $i -eq 10 ]; then
        echo "❌ Services did not become healthy in time."
        echo "   Check logs: docker compose logs"
        exit 1
    fi
done

echo ""
echo "=================================================="
echo "✓ Deployment Complete!"
echo "=================================================="
echo ""
echo "Services:"
echo "  - API:        http://localhost/infer"
echo "  - Health:     http://localhost/healthz"
echo "  - Metrics:    http://localhost/metrics"
echo "  - Grafana:    http://localhost:3000 (admin/admin_change_in_prod)"
echo "  - Prometheus: http://localhost:9090"
echo ""
echo "Quick test:"
echo "  make demo"
echo ""
echo "View logs:"
echo "  docker compose logs -f"
echo ""
echo "⚠️  Remember to:"
echo "  1. Change default passwords in .env"
echo "  2. Configure firewall (ufw/iptables)"
echo "  3. Set up HTTPS for production"
echo "  4. Configure backups"
echo ""
