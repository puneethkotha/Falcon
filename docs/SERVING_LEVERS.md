# Serving levers: measure each, keep or kill

The point of this document is engineering judgment: enable each vLLM lever one at a
time, measure its delta on the frontier at a stated operating point, and decide per
lever with data instead of turning them all on by reflex.

Measure each lever with `benchmarks/guidellm_sweep.sh` at a fixed token profile and
record the delta on TTFT p95, TPOT p95, tokens/sec, and KV-cache %. State the hardware
(e.g. "Modal L4, 24GB, Qwen3-1.7B, prompt 256 / output 256").

## Status of measurements

The deltas below require a GPU host and are **not yet measured** here (no GPU in the
build environment; vLLM's CPU backend is x86-avx-only and does not run on Apple
Silicon). The keep/kill decisions and their rationale are stated now from the design
and the web-verified tradeoffs; fill the numbers with the harness on the GPU host.

## Levers

### 1. Automatic prefix caching  -  DECISION: keep ON

Falcon's classify path (`/infer`) reuses a fixed system prompt on every request, so the
prompt prefix is shared across requests and the KV for it can be reused. This is the
biggest, cheapest win for this workload. Flag: `--enable-prefix-caching`.

Measure prefix-cache hit rate (`vllm:prefix_cache_hits_total / vllm:prefix_cache_queries_total`)
and TTFT with and without a shared prefix.

| Metric | Prefix cache OFF | Prefix cache ON | Delta |
|---|---|---|---|
| TTFT p95 (ms) | _pending GPU_ | _pending GPU_ | |
| Prefix hit rate | ~0 | _pending GPU_ | |
| tokens/sec | _pending GPU_ | _pending GPU_ | |

### 2. Chunked prefill  -  DECISION: keep ON

Interleaves prefill and decode so a long-prompt request does not stall decode of
others. Stabilizes TPOT under mixed prompt lengths. Flag: `--enable-chunked-prefill`.

Verification: TPOT p95 should stay stable when a long-prompt request arrives during a
decode-heavy burst.

| Metric | Chunked prefill OFF | Chunked prefill ON | Delta |
|---|---|---|---|
| TPOT p95 under mixed lengths (ms) | _pending GPU_ | _pending GPU_ | |
| TTFT p95 (ms) | _pending GPU_ | _pending GPU_ | |

### 3. Speculative decoding  -  DECISION: conditional (low-concurrency only)

Web-verified tradeoff: speedups are largest at batch size 1 (up to ~1.8-1.96x decode
speedup) and erode as concurrency grows (~1.2x by batch 128) because decode shifts from
memory-bandwidth-bound to compute-bound; real acceptance rates are ~0.6-0.8. Turning it
on blindly for a throughput benchmark can *lose* throughput.

Decision rule: enable only in the latency-sensitive, low-concurrency regime and cap it
above a batch-size threshold with `--speculative-disable-by-batch-size` (~32). It is OFF
by default in `docker-compose.yml` and `deploy/modal_app.py` because the frontier sweep
is a throughput measurement.

| Metric | Spec decode OFF | Spec decode ON @ batch 1 | Spec decode ON @ batch 32 |
|---|---|---|---|
| TPOT p95 (ms) | _pending GPU_ | _pending GPU_ | _pending GPU_ |
| tokens/sec | _pending GPU_ | _pending GPU_ | _pending GPU_ |
| acceptance rate | n/a | _pending GPU_ | _pending GPU_ |

## Final engine flags (committed)

`docker-compose.yml` (vllm service) and `deploy/modal_app.py`:

```
--model Qwen/Qwen3-1.7B --max-model-len 4096 --enable-prefix-caching --enable-chunked-prefill
```

Speculative decoding is intentionally omitted from the defaults; enable it per the rule
above for a latency-optimized deployment:

```
--speculative-config '{"model":"<draft>","num_speculative_tokens":5}' \
--speculative-disable-by-batch-size 32
```
