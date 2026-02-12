#!/bin/bash
set -e

echo "=================================================="
echo "Failure Injection: Redis Down"
echo "=================================================="
echo ""
echo "This script demonstrates fallback behavior when Redis is unavailable."
echo "The system should continue serving requests without cache/idempotency."
echo ""

# Check if system is running
if ! docker ps | grep -q falcon-redis; then
    echo "❌ Error: Redis is not running. Please start the system first:"
    echo "   make up"
    exit 1
fi

echo "Step 1: Verify Redis is healthy"
echo "----------------------------"
docker exec falcon-redis redis-cli ping
echo ""

echo "Step 2: Send requests with Redis UP (cache should work)"
echo "----------------------------"
for i in {1..3}; do
    response=$(curl -s -X POST http://localhost/infer \
        -H "Content-Type: application/json" \
        -d '{"text": "This text will be cached"}')
    
    cache_hit=$(echo "$response" | jq -r '.cache_hit')
    echo "  Request $i: cache_hit=$cache_hit"
    sleep 0.5
done
echo ""

echo "Step 3: Stop Redis"
echo "----------------------------"
docker stop falcon-redis
echo "✓ Redis stopped"
echo ""

echo "Step 4: Wait for circuit breaker detection"
echo "----------------------------"
sleep 3
echo "✓ Waited 3 seconds"
echo ""

echo "Step 5: Send requests with Redis DOWN (fallback mode)"
echo "----------------------------"
for i in {1..5}; do
    start_time=$(date +%s%3N)
    response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST http://localhost/infer \
        -H "Content-Type: application/json" \
        -d '{"text": "This request will work without Redis"}' 2>/dev/null)
    end_time=$(date +%s%3N)
    duration=$((end_time - start_time))
    
    http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
    
    if [ "$http_code" = "200" ]; then
        worker=$(echo "$response" | grep -v "HTTP_CODE" | jq -r '.worker_id')
        cache_hit=$(echo "$response" | grep -v "HTTP_CODE" | jq -r '.cache_hit')
        echo "  Request $i: ✓ Success (worker=$worker, cache_hit=$cache_hit, ${duration}ms)"
    else
        echo "  Request $i: ❌ Failed (HTTP $http_code)"
    fi
    sleep 0.5
done
echo ""

echo "Step 6: Check fallback metrics"
echo "----------------------------"
echo "Fallback triggers (should be > 0):"
curl -s http://localhost/metrics | grep "fallback_triggered_total" | grep redis || echo "  No fallback metrics yet"
echo ""

echo "Circuit breaker state (should be OPEN=1):"
curl -s http://localhost/metrics | grep "circuit_breaker_state" | grep redis || echo "  No circuit breaker metrics"
echo ""

echo "Step 7: Restart Redis"
echo "----------------------------"
docker start falcon-redis
echo "✓ Redis restarted"
sleep 5
echo "✓ Waiting for Redis to be healthy..."
docker exec falcon-redis redis-cli ping
echo ""

echo "Step 8: Send requests after Redis recovery"
echo "----------------------------"
for i in {1..3}; do
    response=$(curl -s -X POST http://localhost/infer \
        -H "Content-Type: application/json" \
        -d '{"text": "Redis should be back now"}')
    
    cache_hit=$(echo "$response" | jq -r '.cache_hit')
    worker=$(echo "$response" | jq -r '.worker_id')
    echo "  Request $i: worker=$worker, cache_hit=$cache_hit"
    sleep 1
done
echo ""

echo "=================================================="
echo "✓ Failure Injection Complete"
echo "=================================================="
echo ""
echo "Key Observations:"
echo "  1. Requests continued working when Redis was down"
echo "  2. Cache was disabled during outage (all cache_hit=false)"
echo "  3. Circuit breaker opened to prevent retry storms"
echo "  4. Fallback metrics incremented"
echo "  5. System recovered automatically when Redis came back"
echo ""
echo "Check logs for fallback warnings:"
echo "  docker compose logs worker-1 | grep -i fallback"
echo ""
echo "Check Grafana dashboard for circuit breaker state:"
echo "  http://localhost:3000"
echo ""
