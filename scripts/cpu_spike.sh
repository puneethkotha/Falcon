#!/bin/bash
set -e

echo "=================================================="
echo "Failure Injection: CPU Spike"
echo "=================================================="
echo ""
echo "This script creates CPU load on one worker to demonstrate"
echo "load balancing and performance impact."
echo ""

# Check if system is running
if ! docker ps | grep -q falcon-worker; then
    echo "❌ Error: No workers are running. Please start the system first:"
    echo "   make up"
    exit 1
fi

WORKER_NAME="falcon-worker-1"

echo "Step 1: Check baseline CPU usage"
echo "----------------------------"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
    falcon-worker-1 falcon-worker-2 falcon-worker-3
echo ""

echo "Step 2: Create CPU load on $WORKER_NAME"
echo "----------------------------"
echo "Starting CPU stress (4 threads for 60 seconds)..."
docker exec -d $WORKER_NAME sh -c 'apt-get update -qq && apt-get install -y -qq stress-ng && stress-ng --cpu 4 --timeout 60s' 2>/dev/null &
STRESS_PID=$!
sleep 5
echo "✓ CPU stress started"
echo ""

echo "Step 3: Monitor CPU usage during spike"
echo "----------------------------"
for i in {1..5}; do
    echo "Sample $i:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
        falcon-worker-1 falcon-worker-2 falcon-worker-3
    sleep 3
done
echo ""

echo "Step 4: Send requests during CPU spike"
echo "----------------------------"
echo "Observing which workers handle the requests..."
declare -A worker_counts
for i in {1..20}; do
    response=$(curl -s -X POST http://localhost/infer \
        -H "Content-Type: application/json" \
        -d "{\"text\": \"Request during CPU spike $i\"}")
    
    worker=$(echo "$response" | jq -r '.worker_id')
    latency=$(echo "$response" | jq -r '.processing_time_ms')
    
    ((worker_counts[$worker]++))
    echo "  Request $i: $worker (${latency}ms)"
    sleep 0.3
done
echo ""

echo "Request distribution:"
for worker in "${!worker_counts[@]}"; do
    echo "  $worker: ${worker_counts[$worker]} requests"
done
echo ""

echo "Step 5: Wait for CPU stress to complete"
echo "----------------------------"
wait $STRESS_PID 2>/dev/null || true
echo "✓ CPU stress completed"
sleep 5
echo ""

echo "Step 6: Check CPU usage after spike"
echo "----------------------------"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
    falcon-worker-1 falcon-worker-2 falcon-worker-3
echo ""

echo "Step 7: Send requests after recovery"
echo "----------------------------"
declare -A recovery_counts
for i in {1..10}; do
    response=$(curl -s -X POST http://localhost/infer \
        -H "Content-Type: application/json" \
        -d "{\"text\": \"Recovery request $i\"}")
    
    worker=$(echo "$response" | jq -r '.worker_id')
    ((recovery_counts[$worker]++))
done
echo ""

echo "Request distribution after recovery:"
for worker in "${!recovery_counts[@]}"; do
    echo "  $worker: ${recovery_counts[$worker]} requests"
done
echo ""

echo "=================================================="
echo "✓ Failure Injection Complete"
echo "=================================================="
echo ""
echo "Key Observations:"
echo "  1. Worker-1 experienced high CPU load during stress"
echo "  2. Nginx load balancer may have routed fewer requests to busy worker"
echo "  3. System continued serving requests from other workers"
echo "  4. CPU normalized after stress completed"
echo "  5. Load distribution returned to normal after recovery"
echo ""
echo "Check Grafana for:"
echo "  - CPU usage spike on worker-1"
echo "  - Potential latency increase during spike"
echo "  - Request distribution across workers"
echo ""
echo "URL: http://localhost:3000"
echo ""
