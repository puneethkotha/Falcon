"""API routes."""
import json
import time
import uuid
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, Header, HTTPException, status
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response, StreamingResponse

from app.models.schemas import (
    InferenceRequest,
    InferenceResponse,
    BatchInferenceRequest,
    GenerationRequest,
    HealthResponse,
    ReadinessResponse,
    ErrorResponse,
)
from app.services.redis_service import redis_service
from app.services.database_service import database_service
from app.services.inference_service import inference_service, GenerationResult
from app.services.quality_service import quality_service, QualitySample
from app.core.config import settings
from app.core.metrics import (
    inference_requests_total,
    inference_errors_total,
    inference_duration_seconds,
    memory_usage_bytes,
)
from app.utils.circuit_breaker import CircuitBreakerOpenError
from app.utils.hashing import hash_input
import psutil
import os

logger = logging.getLogger(__name__)

router = APIRouter()

# Track uptime
_start_time = time.time()

# Memory ballast for debug mode (MUST BE FALSE IN PROD)
_debug_memory_ballast = []


def _classify_cache_key(text: str) -> str:
    """Hash the full classify request (model + task + text), not just the text."""
    return hash_input({"model": settings.model_id, "task": "classify", "text": text})


def _generation_cache_key(messages, params) -> str:
    """Hash the full generation request so caching is correct across models/params."""
    return hash_input(
        {
            "model": settings.model_id,
            "messages": messages,
            "params": {
                "max_tokens": params.get("max_tokens", settings.default_max_tokens),
                "temperature": params.get("temperature", settings.default_temperature),
                "top_p": params.get("top_p"),
            },
        }
    )


@router.post("/infer", response_model=InferenceResponse)
async def infer(
    request: Request,
    body: InferenceRequest,
    x_idempotency_key: Optional[str] = Header(None),
) -> InferenceResponse:
    """
    Backward-compatible sentiment inference.

    Re-expressed on top of the LLM engine as a constrained classify call, so the
    legacy k6 baseline and demo assets keep working through the migration. Keeps
    response caching, idempotency, structured logging, and Prometheus metrics.
    """
    start_time = time.time()
    request_id = getattr(request.state, "request_id", "unknown")
    client_ip = request.client.host if request.client else None

    cache_hit = False
    idempotency_hit = False
    prediction = None
    confidence = None
    probabilities = None

    try:
        # Idempotency
        if x_idempotency_key and settings.idempotency_enabled:
            cached_response = await redis_service.check_idempotency(x_idempotency_key)
            if cached_response:
                idempotency_hit = True
                response_data = json.loads(cached_response)
                response_data["idempotency_hit"] = True

                await database_service.log_inference_request(
                    request_id=request_id,
                    text_hash=_classify_cache_key(body.text),
                    text_length=len(body.text),
                    prediction=response_data.get("prediction"),
                    confidence=response_data.get("confidence"),
                    probabilities=response_data.get("probabilities"),
                    cache_hit=False,
                    idempotency_hit=True,
                    success=True,
                    processing_time_ms=(time.time() - start_time) * 1000,
                    idempotency_key=x_idempotency_key,
                    client_ip=client_ip,
                    model_id=settings.model_id,
                )
                inference_requests_total.labels(
                    worker_id=settings.worker_id, status="success", cache_hit="idempotency"
                ).inc()
                return InferenceResponse(**response_data)

        # Response cache
        input_hash = _classify_cache_key(body.text)
        if settings.cache_enabled:
            cached_result = await redis_service.get_cache(input_hash)
            if cached_result:
                cache_hit = True
                result_data = json.loads(cached_result)
                prediction = result_data["prediction"]
                confidence = result_data["confidence"]
                probabilities = result_data["probabilities"]

        # Inference (constrained LLM classify)
        if not cache_hit:
            inference_start = time.time()
            prediction, confidence, probabilities = await inference_service.classify(
                body.text
            )
            inference_time_ms = (time.time() - inference_start) * 1000

            if settings.cache_enabled:
                await redis_service.set_cache(
                    input_hash,
                    json.dumps(
                        {
                            "prediction": prediction,
                            "confidence": confidence,
                            "probabilities": probabilities,
                        }
                    ),
                )

            # Sample for online quality observability (async, off critical path).
            if quality_service.should_sample():
                quality_service.submit(
                    QualitySample(
                        request_id=request_id,
                        path="classify",
                        prompt=body.text,
                        output=prediction or "",
                        label=prediction,
                        confidence=confidence,
                        allowed_labels=inference_service.label_names,
                    )
                )
        else:
            inference_time_ms = None

        processing_time_ms = (time.time() - start_time) * 1000
        response = InferenceResponse(
            prediction=prediction,
            confidence=confidence,
            probabilities=probabilities,
            cache_hit=cache_hit,
            worker_id=settings.worker_id,
            processing_time_ms=processing_time_ms,
            idempotency_hit=idempotency_hit,
        )

        if x_idempotency_key and settings.idempotency_enabled:
            await redis_service.store_idempotency(
                x_idempotency_key, response.model_dump_json()
            )

        await database_service.log_inference_request(
            request_id=request_id,
            text_hash=input_hash,
            text_length=len(body.text),
            prediction=prediction,
            confidence=confidence,
            probabilities=probabilities,
            cache_hit=cache_hit,
            idempotency_hit=idempotency_hit,
            success=True,
            processing_time_ms=processing_time_ms,
            inference_time_ms=inference_time_ms,
            idempotency_key=x_idempotency_key,
            client_ip=client_ip,
            model_id=settings.model_id,
        )

        inference_requests_total.labels(
            worker_id=settings.worker_id, status="success", cache_hit=str(cache_hit)
        ).inc()
        inference_duration_seconds.labels(
            worker_id=settings.worker_id, cache_hit=str(cache_hit)
        ).observe(processing_time_ms / 1000.0)

        if settings.debug_memory_growth and settings.debug_memory_growth_mb_per_request > 0:
            _debug_memory_ballast.append(
                bytearray(settings.debug_memory_growth_mb_per_request * 1024 * 1024)
            )

        return response

    except CircuitBreakerOpenError as e:
        return _handle_infer_error(
            e, request_id, client_ip, body, start_time, x_idempotency_key,
            code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except HTTPException:
        raise
    except Exception as e:
        return _handle_infer_error(
            e, request_id, client_ip, body, start_time, x_idempotency_key,
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def _handle_infer_error(e, request_id, client_ip, body, start_time, x_idempotency_key, code):
    error_type = type(e).__name__
    error_message = str(e)
    processing_time_ms = (time.time() - start_time) * 1000

    logger.error(
        f"Inference failed: {e}",
        extra={"request_id": request_id, "error_type": error_type},
    )
    # Fire-and-forget style logging still uses the same buffered path.
    import asyncio

    asyncio.create_task(
        database_service.log_inference_request(
            request_id=request_id,
            text_hash=_classify_cache_key(body.text),
            text_length=len(body.text),
            cache_hit=False,
            success=False,
            processing_time_ms=processing_time_ms,
            error_type=error_type,
            error_message=error_message[:500],
            idempotency_key=x_idempotency_key,
            client_ip=client_ip,
            model_id=settings.model_id,
        )
    )
    inference_requests_total.labels(
        worker_id=settings.worker_id, status="error", cache_hit="false"
    ).inc()
    inference_errors_total.labels(
        worker_id=settings.worker_id, error_type=error_type
    ).inc()
    raise HTTPException(
        status_code=code,
        detail={
            "error": error_message,
            "error_type": error_type,
            "worker_id": settings.worker_id,
            "request_id": request_id,
        },
    )


async def _stream_generation(
    request: Request,
    messages,
    params,
    path: str,
    client_ip: Optional[str],
):
    """Shared streaming path: prime the engine, stream SSE, log + sample on completion.

    Priming (awaiting the first frame before returning the StreamingResponse) lets a
    dead/cold engine surface as a clean 503 instead of a half-open SSE stream.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    start_time = time.time()

    # Deterministic-request cache replay (only when temperature == 0).
    temperature = params.get("temperature", settings.default_temperature)
    cache_key = _generation_cache_key(messages, params) if temperature == 0 else None
    if cache_key and settings.cache_enabled:
        cached = await redis_service.get_cache(cache_key)
        if cached:
            async def _replay():
                yield f"data: {json.dumps(_openai_chunk(cached, finish='stop'))}\n\n"
                yield "data: [DONE]\n\n"

            inference_requests_total.labels(
                worker_id=settings.worker_id, status="success", cache_hit="True"
            ).inc()
            return StreamingResponse(_replay(), media_type="text/event-stream")

    result = GenerationResult()
    gen = inference_service.stream(messages, params, result=result)

    try:
        first_frame = await gen.__anext__()
    except CircuitBreakerOpenError:
        inference_errors_total.labels(
            worker_id=settings.worker_id, error_type="CircuitBreakerOpenError"
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "LLM engine circuit breaker open",
                "error_type": "CircuitBreakerOpenError",
                "worker_id": settings.worker_id,
                "request_id": request_id,
            },
        )
    except StopAsyncIteration:
        first_frame = "data: [DONE]\n\n"
    except Exception as e:
        inference_errors_total.labels(
            worker_id=settings.worker_id, error_type=type(e).__name__
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": str(e),
                "error_type": type(e).__name__,
                "worker_id": settings.worker_id,
                "request_id": request_id,
            },
        )

    async def _body():
        yield first_frame
        try:
            async for frame in gen:
                yield frame
        finally:
            await _finalize_generation(
                request_id, path, messages, params, result, start_time, cache_key, client_ip
            )

    inference_requests_total.labels(
        worker_id=settings.worker_id, status="success", cache_hit="False"
    ).inc()
    return StreamingResponse(_body(), media_type="text/event-stream")


async def _finalize_generation(
    request_id, path, messages, params, result, start_time, cache_key, client_ip
):
    processing_time_ms = (time.time() - start_time) * 1000
    prompt_text = messages[-1]["content"] if messages else ""

    if cache_key and settings.cache_enabled and result.text:
        await redis_service.set_cache(cache_key, result.text)

    await database_service.log_inference_request(
        request_id=request_id,
        text_hash=cache_key or hash_input({"model": settings.model_id, "messages": messages}),
        text_length=len(prompt_text),
        cache_hit=False,
        success=True,
        processing_time_ms=processing_time_ms,
        inference_time_ms=result.generation_ms,
        client_ip=client_ip,
        model_id=settings.model_id,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        ttft_ms=result.ttft_ms,
        generation_ms=result.generation_ms,
    )

    if quality_service.should_sample():
        quality_service.submit(
            QualitySample(
                request_id=request_id,
                path=path,
                prompt=prompt_text,
                output=result.text,
                finish_reason=result.finish_reason,
            )
        )


def _openai_chunk(content: str, finish: Optional[str] = None) -> dict:
    """Minimal OpenAI-compatible streaming chunk (used for cache replay)."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion.chunk",
        "model": settings.model_id,
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": finish}],
    }


@router.post("/generate")
async def generate(request: Request, body: GenerationRequest):
    """Falcon-native streaming generation (SSE), protected by the vLLM breaker."""
    client_ip = request.client.host if request.client else None
    messages = body.as_messages()
    params = body.sampling_params()
    if not body.stream:
        text, result = await inference_service.generate_text(messages, params)
        return {
            "text": text,
            "model": settings.model_id,
            "worker_id": settings.worker_id,
            "ttft_ms": result.ttft_ms,
            "generation_ms": result.generation_ms,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "finish_reason": result.finish_reason,
        }
    return await _stream_generation(request, messages, params, "generate", client_ip)


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """OpenAI-compatible chat completions, proxied through Falcon's chassis.

    Streaming requests get SSE with token-level timings recorded; non-streaming
    requests get a standard ChatCompletion JSON body.
    """
    client_ip = request.client.host if request.client else None
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    messages = body.get("messages")
    if not messages:
        raise HTTPException(status_code=400, detail="'messages' is required")

    params = {}
    for key in ("max_tokens", "temperature", "top_p", "stop", "presence_penalty", "frequency_penalty"):
        if key in body:
            params[key] = body[key]

    stream = body.get("stream", False)
    if stream:
        return await _stream_generation(request, messages, params, "generate", client_ip)

    text, result = await inference_service.generate_text(messages, params)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "model": settings.model_id,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": result.finish_reason or "stop",
            }
        ],
        "usage": {
            "prompt_tokens": result.prompt_tokens or 0,
            "completion_tokens": result.completion_tokens or 0,
            "total_tokens": (result.prompt_tokens or 0) + (result.completion_tokens or 0),
        },
    }


@router.post("/infer/batch")
async def infer_batch(
    request: Request,
    body: BatchInferenceRequest,
) -> dict:
    """
    Batch classify on multiple texts (simplified, no per-item cache/idempotency).
    """
    start_time = time.time()
    results = []

    for text in body.texts[:50]:  # cap at 50
        try:
            t0 = time.time()
            prediction, confidence, probabilities = await inference_service.classify(text)
            dur_ms = (time.time() - t0) * 1000
            results.append(
                {
                    "text": text[:100] + ("..." if len(text) > 100 else ""),
                    "prediction": prediction,
                    "confidence": confidence,
                    "probabilities": probabilities,
                    "processing_time_ms": dur_ms,
                    "worker_id": settings.worker_id,
                }
            )
        except Exception as e:
            results.append({"text": text[:100], "error": str(e), "worker_id": settings.worker_id})

    total_ms = (time.time() - start_time) * 1000
    return {
        "results": results,
        "total_count": len(results),
        "total_time_ms": round(total_ms, 2),
        "worker_id": settings.worker_id,
    }


@router.get("/healthz", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint. Returns 200 if the service is alive."""
    uptime = time.time() - _start_time
    return HealthResponse(
        status="healthy",
        worker_id=settings.worker_id,
        timestamp=datetime.utcnow(),
        uptime_seconds=uptime,
    )


@router.get("/readyz", response_model=ReadinessResponse)
async def readiness_check() -> ReadinessResponse:
    """
    Readiness check endpoint.

    Checks the LLM engine, Redis, and Postgres. The engine is required for
    readiness; Redis and Postgres are non-blocking dependencies with fallbacks.
    """
    engine_ok = await inference_service.engine_probe()
    checks = {
        "engine_ready": engine_ok,
        "model_loaded": await inference_service.health_check(),
        "redis_available": await redis_service.health_check(),
        "database_available": await database_service.health_check(),
    }
    ready = checks["engine_ready"]

    return ReadinessResponse(
        ready=ready,
        worker_id=settings.worker_id,
        checks=checks,
        timestamp=datetime.utcnow(),
    )


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    process = psutil.Process(os.getpid())
    memory_usage_bytes.labels(worker_id=settings.worker_id).set(process.memory_info().rss)
    database_service.update_pool_metrics()
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
