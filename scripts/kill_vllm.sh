#!/bin/bash
set -e

# Failure injection: kill the vLLM engine and show the chassis degrade cleanly.
#
# Expected behavior (the engine is a protected dependency, like Redis/Postgres):
#   - streaming/generate requests return a structured 502 while the engine is gone,
#   - after CIRCUIT_BREAKER_FAILURE_THRESHOLD failures the vllm breaker opens and
#     requests return 503 immediately (no hang),
#   - circuit_breaker_state{dependency="vllm"} goes to 1 (OPEN),
#   - the /infer classify path fails the same way (it uses the same engine),
#   - after the engine restarts, the breaker half-opens and recovers.

echo "=================================================="
echo "Failure Injection: Kill vLLM engine"
echo "=================================================="

if ! docker ps | grep -q falcon-vllm; then
    echo "Note: falcon-vllm is not running (start it with: docker compose --profile gpu up -d vllm)."
    echo "On a GPU-less host, run tools/mock_vllm_server.py to exercise this drill."
fi

echo "Step 1: baseline breaker state"
curl -s http://localhost/metrics | grep 'circuit_breaker_state' | grep 'vllm' | grep -v '^#' || true
echo

echo "Step 2: kill the engine"
docker kill falcon-vllm 2>/dev/null && echo "engine killed" || echo "engine container not found; skipping kill"
echo

echo "Step 3: send requests during the outage (expect 502 then 503 once the breaker opens)"
for i in $(seq 1 8); do
    code=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost/generate \
        -H "Content-Type: application/json" \
        -d '{"prompt":"hello","max_tokens":8}' 2>/dev/null)
    echo "  request $i -> HTTP $code"
    sleep 0.3
done
echo

echo "Step 4: breaker state after outage (1 = OPEN)"
curl -s http://localhost/metrics | grep 'circuit_breaker_state' | grep 'vllm' | grep -v '^#' || true
echo

echo "Step 5: restart the engine and let the breaker recover"
docker start falcon-vllm 2>/dev/null && echo "engine restarting..." || echo "no engine container to restart"
echo
echo "Watch recovery in Grafana: http://localhost:3000 (Falcon LLM Serving dashboard)"
echo "=================================================="
