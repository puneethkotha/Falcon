"""Mock OpenAI-compatible engine for LOCAL DEVELOPMENT AND CI ONLY.

This is NOT vLLM and NOT a model. It is a tiny test double that speaks the subset
of the OpenAI API that Falcon's worker uses (/v1/models, /v1/chat/completions with
streaming, /metrics). Its purpose is to exercise Falcon's streaming path, TTFT/ITL
metrics, circuit breaker, and quality sidecar on hardware without a GPU (e.g. an
Apple Silicon laptop) where the real vLLM CPU backend (x86 avx512/avx2) cannot run.

It emits deterministic canned text with small per-token delays so that TTFT and
inter-token latency are measurable. Any latency observed against this server is a
property of the mock, NOT a benchmark of vLLM. Real throughput/latency numbers must
come from vLLM on the GPU/x86 host (see benchmarks/ and docs/frontier/).

Run:  python -m uvicorn tools.mock_vllm_server:app --port 8000
"""
import asyncio
import json
import time
import uuid
from typing import List

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, StreamingResponse

app = FastAPI(title="mock-openai-engine")

MODEL_ID = "Qwen/Qwen3-0.6B"
TTFT_DELAY_S = 0.10
ITL_DELAY_S = 0.02

# Minimal vLLM-shaped metrics so the Prometheus scrape job and Grafana panels can be
# validated end-to-end without a real engine. Values are static placeholders.
_METRICS = """# HELP vllm:num_requests_running Number of requests currently running.
# TYPE vllm:num_requests_running gauge
vllm:num_requests_running{model_name="Qwen/Qwen3-0.6B"} 1.0
# HELP vllm:num_requests_waiting Number of requests waiting to be processed.
# TYPE vllm:num_requests_waiting gauge
vllm:num_requests_waiting{model_name="Qwen/Qwen3-0.6B"} 0.0
# HELP vllm:gpu_cache_usage_perc KV-cache usage (0-1).
# TYPE vllm:gpu_cache_usage_perc gauge
vllm:gpu_cache_usage_perc{model_name="Qwen/Qwen3-0.6B"} 0.12
# HELP vllm:prefix_cache_queries_total Prefix cache queries.
# TYPE vllm:prefix_cache_queries_total counter
vllm:prefix_cache_queries_total{model_name="Qwen/Qwen3-0.6B"} 100.0
# HELP vllm:prefix_cache_hits_total Prefix cache hits.
# TYPE vllm:prefix_cache_hits_total counter
vllm:prefix_cache_hits_total{model_name="Qwen/Qwen3-0.6B"} 63.0
# HELP vllm:generation_tokens_total Generation tokens produced.
# TYPE vllm:generation_tokens_total counter
vllm:generation_tokens_total{model_name="Qwen/Qwen3-0.6B"} 12000.0
"""


def _tokens_for(messages: List[dict]) -> List[str]:
    system = " ".join(m.get("content", "") for m in messages if m.get("role") == "system").lower()
    user = " ".join(m.get("content", "") for m in messages if m.get("role") == "user")
    if "sentiment classifier" in system:
        text = user.lower()
        pos = any(w in text for w in ("great", "excellent", "amazing", "love", "best", "good", "fantastic", "outstanding", "exceeded", "recommend"))
        neg = any(w in text for w in ("terrible", "bad", "worst", "hate", "poor", "awful", "broken", "waste", "disappointing"))
        label = "positive" if pos and not neg else "negative" if neg and not pos else "neutral"
        return [label]
    return ("Falcon is a reliability chassis that now serves a real language model "
            "through vLLM behind Nginx with token level metrics.").split()


@app.get("/v1/models")
async def models():
    return {"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]}


@app.get("/metrics")
async def metrics():
    from starlette.responses import Response
    return Response(content=_METRICS, media_type="text/plain; version=0.0.4")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    max_tokens = int(body.get("max_tokens", 256))
    tokens = _tokens_for(messages)[:max_tokens]
    prompt_tokens = sum(len(m.get("content", "").split()) for m in messages)
    cmpl_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    if not stream:
        return JSONResponse(
            {
                "id": cmpl_id,
                "object": "chat.completion",
                "created": created,
                "model": MODEL_ID,
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": " ".join(tokens)}, "finish_reason": "stop"}
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": len(tokens),
                    "total_tokens": prompt_tokens + len(tokens),
                },
            }
        )

    include_usage = bool((body.get("stream_options") or {}).get("include_usage"))

    async def event_stream():
        await asyncio.sleep(TTFT_DELAY_S)
        for i, tok in enumerate(tokens):
            piece = tok if i == 0 else " " + tok
            chunk = {
                "id": cmpl_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": MODEL_ID,
                "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(chunk)}\n\n"
            await asyncio.sleep(ITL_DELAY_S)
        final = {
            "id": cmpl_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": MODEL_ID,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        if include_usage:
            final["usage"] = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": len(tokens),
                "total_tokens": prompt_tokens + len(tokens),
            }
        yield f"data: {json.dumps(final)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
