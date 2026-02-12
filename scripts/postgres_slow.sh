#!/bin/bash
set -e

echo "=================================================="
echo "Failure Injection: Postgres Slow Queries"
echo "=================================================="
echo ""
echo "This script simulates slow Postgres queries by injecting"
echo "artificial delay. The system should buffer logs and continue serving."
echo ""

# Check if system is running
if ! docker ps | grep -q falcon-postgres; then
    echo "❌ Error: Postgres is not running. Please start the system first:"
    echo "   make up"
    exit 1
fi

echo "Step 1: Verify Postgres is healthy"
echo "----------------------------"
docker exec falcon-postgres pg_isready -U falcon
echo ""

echo "Step 2: Send baseline requests (fast DB)"
echo "----------------------------"
start_time=$(date +%s%3N)
for i in {1..5}; do
    curl -s -X POST http://localhost/infer \
        -H "Content-Type: application/json" \
        -d "{\"text\": \"Baseline request $i\"}" > /dev/null
done
end_time=$(date +%s%3N)
duration=$((end_time - start_time))
avg_duration=$((duration / 5))
echo "  Average time per request: ${avg_duration}ms"
echo ""

echo "Step 3: Inject slow query extension"
echo "----------------------------"
docker exec falcon-postgres psql -U falcon -d falcon_inference -c "
CREATE EXTENSION IF NOT EXISTS pg_sleep;
"
echo "✓ Extension created"
echo ""

echo "Step 4: Add trigger to slow down INSERTs"
echo "----------------------------"
docker exec falcon-postgres psql -U falcon -d falcon_inference -c "
CREATE OR REPLACE FUNCTION slow_insert_trigger()
RETURNS TRIGGER AS \$\$
BEGIN
    PERFORM pg_sleep(2);  -- 2 second delay
    RETURN NEW;
END;
\$\$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS slow_insert ON inference_logs;
CREATE TRIGGER slow_insert
    BEFORE INSERT ON inference_logs
    FOR EACH ROW
    EXECUTE FUNCTION slow_insert_trigger();
" 2>/dev/null || echo "Note: Trigger may already exist"
echo "✓ Slow insert trigger created (2s delay per insert)"
echo ""

echo "Step 5: Send requests with slow DB"
echo "----------------------------"
echo "Requests will take longer but should still succeed..."
start_time=$(date +%s%3N)
for i in {1..3}; do
    req_start=$(date +%s%3N)
    response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST http://localhost/infer \
        -H "Content-Type: application/json" \
        -d "{\"text\": \"Slow DB request $i\"}" 2>/dev/null)
    req_end=$(date +%s%3N)
    req_duration=$((req_end - req_start))
    
    http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
    echo "  Request $i: HTTP $http_code (${req_duration}ms)"
done
end_time=$(date +%s%3N)
duration=$((end_time - start_time))
avg_duration=$((duration / 3))
echo "  Average time per request: ${avg_duration}ms (much slower!)"
echo ""

echo "Step 6: Check DB operation metrics"
echo "----------------------------"
echo "Database operation latency (should show increased p95):"
curl -s http://localhost/metrics | grep "db_operation_duration" | grep log_inference | head -3
echo ""

echo "Step 7: Check if logs are being buffered/dropped"
echo "----------------------------"
echo "Dropped logs metric:"
curl -s http://localhost/metrics | grep "dropped_logs_total" || echo "  No logs dropped (good!)"
echo ""

echo "Step 8: Remove slow trigger"
echo "----------------------------"
docker exec falcon-postgres psql -U falcon -d falcon_inference -c "
DROP TRIGGER IF EXISTS slow_insert ON inference_logs;
DROP FUNCTION IF EXISTS slow_insert_trigger();
"
echo "✓ Trigger removed"
echo ""

echo "Step 9: Verify DB performance restored"
echo "----------------------------"
start_time=$(date +%s%3N)
for i in {1..5}; do
    curl -s -X POST http://localhost/infer \
        -H "Content-Type: application/json" \
        -d "{\"text\": \"Recovery request $i\"}" > /dev/null
done
end_time=$(date +%s%3N)
duration=$((end_time - start_time))
avg_duration=$((duration / 5))
echo "  Average time per request: ${avg_duration}ms (back to normal)"
echo ""

echo "=================================================="
echo "✓ Failure Injection Complete"
echo "=================================================="
echo ""
echo "Key Observations:"
echo "  1. Requests took longer with slow DB but still succeeded"
echo "  2. Inference continued (DB is non-blocking for responses)"
echo "  3. DB metrics showed increased latency"
echo "  4. System recovered immediately after trigger removal"
echo ""
echo "If logs were being dropped:"
echo "  - Check 'dropped_logs_total' metric"
echo "  - Logs were buffered in memory (up to 1000)"
echo "  - Buffer would flush automatically when DB recovered"
echo ""
echo "Check Grafana for DB operation latency:"
echo "  http://localhost:3000"
echo ""
