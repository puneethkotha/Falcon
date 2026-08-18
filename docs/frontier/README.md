# Throughput-vs-latency frontier

The headline artifact for the LLM-serving upgrade: a curve of achieved throughput
(output tokens/sec) against latency (TTFT p95 and TPOT p95) as offered load rises,
with the knee marked and the max-sustainable rate at a chosen SLO.

## Status

The frontier is GPU-dependent and is **not yet measured**. This directory holds the
reproducible harness and a clearly-labelled synthetic example that proves the
tooling runs. Do not read `EXAMPLE_synthetic_frontier.png` as a measurement.

Real numbers require a GPU host (no GPU exists in the dev environment where this was
built, and vLLM's CPU backend is x86 avx-only and will not run on Apple Silicon).

## Reproduce (GPU host)

Pin the hardware and token profile so numbers are comparable. State the exact instance
(e.g. "Modal L4, 24GB"), model, quantization, input length, and output length for every
reported number.

```bash
# 1. Serve the model (Modal scale-to-zero, RunPod, or a local GPU box)
docker compose --profile gpu up -d vllm        # or deploy/modal_app.py

# 2. Sweep from synchronous (latency floor) to saturation (throughput ceiling)
pip install -r benchmarks/requirements-bench.txt
TARGET=http://localhost/v1 MODEL=Qwen/Qwen3-1.7B \
  PROMPT_TOKENS=256 OUTPUT_TOKENS=256 MAX_SECONDS=120 \
  ./benchmarks/guidellm_sweep.sh
# report -> docs/frontier/Qwen-Qwen3-1.7B-sweep.json

# 3. Cross-check two fixed rates with the engine's own tool
vllm bench serve --model Qwen/Qwen3-1.7B --request-rate 8 --num-prompts 200

# 4. Plot the frontier + compute cost/1M output tokens at the operating point
python benchmarks/plot_frontier.py docs/frontier/Qwen-Qwen3-1.7B-sweep.json \
  --gpu-price-per-hour 0.80 --ttft-slo-ms 500 --tpot-slo-ms 50 \
  --out docs/frontier/frontier.png
```

## What to report

- TTFT p50/p95/p99 (guidellm client-side, cross-checked with `vllm:time_to_first_token_seconds`
  and Falcon's `falcon_ttft_seconds`).
- TPOT/ITL p50/p95 (`vllm:time_per_output_token_seconds`). Identity used:
  `TPOT = (e2e - TTFT) / (output_tokens - 1)`; with single-token chunks ITL approximates TPOT.
- System output tokens/sec = `rate(vllm:generation_tokens_total[1m])`; the knee and the
  max-RPS-at-SLO.
- Cost per 1M output tokens = (active GPU-seconds x per-second price) / output tokens at the
  operating point. Idle cost is $0 on scale-to-zero, so a portfolio demo's bill is dominated
  by cold starts, not tokens.

## Tooling self-test (no GPU)

```bash
pip install matplotlib
python benchmarks/plot_frontier.py --self-test --out docs/frontier/EXAMPLE_synthetic_frontier.png
```
