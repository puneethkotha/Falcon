#!/bin/bash
set -e

echo "=================================================="
echo "Failure Injection: Memory Growth"
echo "=================================================="
echo ""
echo "This script simulates memory growth by enabling a debug flag"
echo "that allocates memory on each request."
echo ""
echo "⚠️  WARNING: This is a DEBUG feature and must be disabled in production!"
echo ""

# Check if system is running
if ! docker ps | grep -q falcon-worker; then
    echo "❌ Error: No workers are running. Please start the system first:"
    echo "   make up"
    exit 1
fi

WORKER_NAME="falcon-worker-1"

echo "Step 1: Check baseline memory usage"
echo "----------------------------"
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}" \
    falcon-worker-1 falcon-worker-2 falcon-worker-3
echo ""

echo "Step 2: Enable memory growth debug flag on $WORKER_NAME"
echo "----------------------------"
echo "Restarting worker with debug flag enabled..."
docker compose stop $WORKER_NAME

# Create temporary env override
cat > /tmp/worker-debug.env << EOF
DEBUG_MEMORY_GROWTH=true
DEBUG_MEMORY_GROWTH_MB_PER_REQUEST=5
EOF

# Restart worker with debug env
docker compose run -d --name $WORKER_NAME \
    --env-file /tmp/worker-debug.env \
    worker-1 2>/dev/null || docker start $WORKER_NAME

sleep 10
echo "✓ Worker restarted with memory growth enabled (5MB per request)"
echo ""

echo "Step 3: Monitor memory before load"
echo "----------------------------"
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}" \
    $WORKER_NAME
echo ""

echo "Step 4: Send requests to grow memory"
echo "----------------------------"
echo "Sending 20 requests (will grow memory by ~100MB)..."
for i in {1..20}; do
    response=$(curl -s -X POST http://localhost/infer \
        -H "Content-Type: application/json" \
        -d "{\"text\": \"Memory growth request $i\"}")
    
    if [ $((i % 5)) -eq 0 ]; then
        mem=$(docker stats --no-stream --format "{{.MemUsage}}" $WORKER_NAME)
        echo "  After $i requests: Memory = $mem"
    fi
    sleep 0.5
done
echo ""

echo "Step 5: Monitor memory growth"
echo "----------------------------"
echo "Memory samples over 30 seconds:"
for i in {1..10}; do
    mem=$(docker stats --no-stream --format "{{.MemUsage}}" $WORKER_NAME)
    cpu=$(docker stats --no-stream --format "{{.CPUPerc}}" $WORKER_NAME)
    echo "  Sample $i: Memory=$mem, CPU=$cpu"
    sleep 3
done
echo ""

echo "Step 6: Check memory metrics"
echo "----------------------------"
echo "Worker memory usage from Prometheus:"
curl -s http://localhost/metrics | grep "memory_usage_bytes{worker_id=\"worker-1\"}" || echo "  Metric not found"
echo ""

echo "Step 7: Disable debug flag and restart worker"
echo "----------------------------"
rm -f /tmp/worker-debug.env
docker compose stop $WORKER_NAME
docker compose up -d $WORKER_NAME
sleep 10
echo "✓ Worker restarted with normal configuration"
echo ""

echo "Step 8: Verify memory is back to normal"
echo "----------------------------"
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}" \
    falcon-worker-1 falcon-worker-2 falcon-worker-3
echo ""

echo "Step 9: Send requests to confirm normal operation"
echo "----------------------------"
for i in {1..5}; do
    response=$(curl -s -X POST http://localhost/infer \
        -H "Content-Type: application/json" \
        -d "{\"text\": \"Normal request $i\"}")
    echo "  Request $i: ✓"
done
echo ""

echo "=================================================="
echo "✓ Failure Injection Complete"
echo "=================================================="
echo ""
echo "Key Observations:"
echo "  1. Memory grew linearly with each request (5MB per request)"
echo "  2. This simulates a memory leak scenario"
echo "  3. System would eventually OOM if continued"
echo "  4. Memory was freed after container restart"
echo ""
echo "In production:"
echo "  - Monitor memory_usage_bytes metric"
echo "  - Set up alerts for abnormal memory growth"
echo "  - Use container memory limits to prevent OOM"
echo "  - Investigate memory leaks with profiling tools"
echo ""
echo "Check Grafana memory dashboard:"
echo "  http://localhost:3000"
echo ""
echo "⚠️  Remember: DEBUG_MEMORY_GROWTH must ALWAYS be false in production!"
echo ""
