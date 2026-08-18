#!/usr/bin/env bash
#
# Throughput-vs-latency frontier sweep with guidellm (the vLLM-project benchmarker).
#
# Sweeps offered load from synchronous (one-at-a-time, the latency floor) up to
# saturation (max concurrency, the throughput ceiling), holding a fixed input/output
# token profile so runs are comparable. guidellm reports TTFT, ITL, TPOT, and
# per-rate throughput and writes a JSON report that benchmarks/plot_frontier.py turns
# into the committed frontier plot.
#
# Run this against the engine (through Nginx at /v1 so the whole chassis is measured,
# or directly against the engine to isolate it). Requires a GPU host for meaningful
# numbers; see docs/frontier/README.md for the exact reproduction recipe.
#
# Usage:
#   TARGET=http://localhost/v1 MODEL=Qwen/Qwen3-1.7B ./benchmarks/guidellm_sweep.sh
set -euo pipefail

TARGET="${TARGET:-http://localhost/v1}"
MODEL="${MODEL:-Qwen/Qwen3-1.7B}"
PROMPT_TOKENS="${PROMPT_TOKENS:-256}"
OUTPUT_TOKENS="${OUTPUT_TOKENS:-256}"
MAX_SECONDS="${MAX_SECONDS:-120}"
OUT="${OUT:-docs/frontier/$(echo "${MODEL}" | tr '/' '-')-sweep.json}"

mkdir -p "$(dirname "${OUT}")"

echo "Sweeping ${MODEL} at ${TARGET}"
echo "  token profile: prompt=${PROMPT_TOKENS} output=${OUTPUT_TOKENS}, ${MAX_SECONDS}s/rate"
echo "  report -> ${OUT}"

guidellm benchmark \
  --target "${TARGET}" \
  --model "${MODEL}" \
  --rate-type sweep \
  --data "{\"prompt_tokens\":${PROMPT_TOKENS},\"output_tokens\":${OUTPUT_TOKENS}}" \
  --max-seconds "${MAX_SECONDS}" \
  --output-path "${OUT}"

echo "Cross-check two fixed rates with the engine's own tool:"
echo "  vllm bench serve --model ${MODEL} --request-rate 8 --num-prompts 200"
echo
echo "Plot the frontier:"
echo "  python benchmarks/plot_frontier.py ${OUT} --gpu-price-per-hour 0.80 \\"
echo "    --ttft-slo-ms 500 --tpot-slo-ms 50 --out docs/frontier/frontier.png"
