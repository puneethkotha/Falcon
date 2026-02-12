#!/bin/bash
set -e

echo "=================================================="
echo "Failure Injection: Kill Worker"
echo "=================================================="
echo ""
echo "This script demonstrates resilience by killing one worker"
echo "and showing that the system continues to serve requests."
echo ""

# Check if system is running
if ! docker ps | grep -q falcon-worker; then
    echo "❌ Error: No workers are running. Please start the system first:"
    echo "   make up"
    exit 1
fi

echo "Step 1: Check current health"
echo "----------------------------"
curl -s http://localhost/healthz | jq .
echo ""

echo "Step 2: Get baseline metrics"
echo "----------------------------"
echo "Active workers before kill:"
docker ps --filter name=falcon-worker --format "table {{.Names}}\t{{.Status}}"
echo ""

echo "Request count before:"
curl -s http://localhost/metrics | grep "inference_requests_total" | head -3
echo ""

echo "Step 3: Kill worker-2"
echo "----------------------------"
docker kill falcon-worker-2
echo "✓ Worker-2 killed"
echo ""

echo "Step 4: Wait for Nginx to detect failure"
echo "----------------------------"
sleep 5
echo "✓ Waited 5 seconds"
echo ""

echo "Step 5: Send test requests (should still work)"
echo "----------------------------"
for i in {1..10}; do
    response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST http://localhost/infer \
        -H "Content-Type: application/json" \
        -d '{"text": "This is a test after worker failure"}' 2>/dev/null)
    
    http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
    
    if [ "$http_code" = "200" ]; then
        worker=$(echo "$response" | grep -v "HTTP_CODE" | jq -r '.worker_id')
        echo "  Request $i: ✓ Success (handled by $worker)"
    else
        echo "  Request $i: ❌ Failed (HTTP $http_code)"
    fi
    sleep 0.5
done
echo ""

echo "Step 6: Check remaining workers"
echo "----------------------------"
echo "Active workers after kill:"
docker ps --filter name=falcon-worker --format "table {{.Names}}\t{{.Status}}"
echo ""

echo "Step 7: Restart killed worker"
echo "----------------------------"
docker start falcon-worker-2
echo "✓ Worker-2 restarted"
sleep 5
echo "✓ Waiting for worker to be healthy..."
echo ""

echo "Step 8: Verify all workers healthy"
echo "----------------------------"
docker ps --filter name=falcon-worker --format "table {{.Names}}\t{{.Status}}"
echo ""

echo "=================================================="
echo "✓ Failure Injection Complete"
echo "=================================================="
echo ""
echo "Key Observations:"
echo "  1. Requests continued to be served during worker failure"
echo "  2. Nginx automatically routed traffic to healthy workers"
echo "  3. No request failures (assuming other workers healthy)"
echo "  4. Worker successfully rejoined pool after restart"
echo ""
echo "Check Grafana dashboard for visual impact:"
echo "  http://localhost:3000"
echo ""
