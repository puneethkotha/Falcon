"""API routes."""
import json
import time
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, Header, HTTPException, status
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from app.models.schemas import (
    InferenceRequest,
    InferenceResponse,
    HealthResponse,
    ReadinessResponse,
    ErrorResponse,
)
from app.services.redis_service import redis_service
from app.services.database_service import database_service
from app.services.inference_service import inference_service
from app.core.config import settings
from app.core.metrics import (
    inference_requests_total,
    inference_errors_total,
    inference_duration_seconds,
    memory_usage_bytes,
)
from app.utils.hashing import hash_input
import psutil
import os

logger = logging.getLogger(__name__)

router = APIRouter()

# Track uptime
_start_time = time.time()

# Memory ballast for debug mode (MUST BE FALSE IN PROD)
_debug_memory_ballast = []


@router.post("/infer", response_model=InferenceResponse)
async def infer(
    request: Request,
    body: InferenceRequest,
    x_idempotency_key: Optional[str] = Header(None),
) -> InferenceResponse:
    """
    Perform ML inference on input text.
    
    Supports:
    - Response caching based on input hash
    - Idempotency via X-Idempotency-Key header
    - Structured logging
    - Prometheus metrics
    """
    start_time = time.time()
    request_id = getattr(request.state, "request_id", "unknown")
    client_ip = request.client.host if request.client else None
    
    cache_hit = False
    idempotency_hit = False
    prediction = None
    confidence = None
    probabilities = None
    error_type = None
    error_message = None
    
    try:
        # Check idempotency first
        if x_idempotency_key and settings.idempotency_enabled:
            cached_response = await redis_service.check_idempotency(
                x_idempotency_key
            )
            if cached_response:
                idempotency_hit = True
                response_data = json.loads(cached_response)
                response_data["idempotency_hit"] = True
                
                # Log to database
                await database_service.log_inference_request(
                    request_id=request_id,
                    text_hash=hash_input({"text": body.text}),
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
                )
                
                # Update metrics
                inference_requests_total.labels(
                    worker_id=settings.worker_id,
                    status="success",
                    cache_hit="idempotency",
                ).inc()
                
                return InferenceResponse(**response_data)
        
        # Check cache
        input_hash = hash_input({"text": body.text})
        if settings.cache_enabled:
            cached_result = await redis_service.get_cache(input_hash)
            if cached_result:
                cache_hit = True
                result_data = json.loads(cached_result)
                prediction = result_data["prediction"]
                confidence = result_data["confidence"]
                probabilities = result_data["probabilities"]
                
                logger.info(
                    "Cache hit",
                    extra={
                        "request_id": request_id,
                        "input_hash": input_hash,
                        "prediction": prediction,
                    },
                )
        
        # Perform inference if not cached
        if not cache_hit:
            inference_start = time.time()
            prediction, confidence, probabilities = await inference_service.predict(
                body.text
            )
            inference_time_ms = (time.time() - inference_start) * 1000
            
            logger.info(
                "Inference completed",
                extra={
                    "request_id": request_id,
                    "inference_time_ms": inference_time_ms,
                    "prediction": prediction,
                    "confidence": confidence,
                },
            )
            
            # Cache result
            if settings.cache_enabled:
                cache_data = {
                    "prediction": prediction,
                    "confidence": confidence,
                    "probabilities": probabilities,
                }
                await redis_service.set_cache(
                    input_hash,
                    json.dumps(cache_data),
                )
        else:
            inference_time_ms = None
        
        # Build response
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
        
        # Store idempotency if key provided
        if x_idempotency_key and settings.idempotency_enabled:
            response_json = response.model_dump_json()
            await redis_service.store_idempotency(
                x_idempotency_key,
                response_json,
            )
        
        # Log to database
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
        )
        
        # Update metrics
        inference_requests_total.labels(
            worker_id=settings.worker_id,
            status="success",
            cache_hit=str(cache_hit),
        ).inc()
        
        inference_duration_seconds.labels(
            worker_id=settings.worker_id,
            cache_hit=str(cache_hit),
        ).observe(processing_time_ms / 1000.0)
        
        # Debug memory growth (MUST BE FALSE IN PROD)
        if settings.debug_memory_growth and settings.debug_memory_growth_mb_per_request > 0:
            _debug_memory_ballast.append(
                bytearray(settings.debug_memory_growth_mb_per_request * 1024 * 1024)
            )
            logger.warning(
                "DEBUG: Memory ballast added",
                extra={"ballast_mb": settings.debug_memory_growth_mb_per_request},
            )
        
        return response
        
    except Exception as e:
        error_type = type(e).__name__
        error_message = str(e)
        processing_time_ms = (time.time() - start_time) * 1000
        
        logger.error(
            f"Inference failed: {e}",
            extra={
                "request_id": request_id,
                "error_type": error_type,
                "error_message": error_message,
                "processing_time_ms": processing_time_ms,
            },
        )
        
        # Log error to database
        await database_service.log_inference_request(
            request_id=request_id,
            text_hash=hash_input({"text": body.text}),
            text_length=len(body.text),
            cache_hit=False,
            idempotency_hit=idempotency_hit,
            success=False,
            processing_time_ms=processing_time_ms,
            error_type=error_type,
            error_message=error_message[:500],
            idempotency_key=x_idempotency_key,
            client_ip=client_ip,
        )
        
        # Update metrics
        inference_requests_total.labels(
            worker_id=settings.worker_id,
            status="error",
            cache_hit="false",
        ).inc()
        
        inference_errors_total.labels(
            worker_id=settings.worker_id,
            error_type=error_type,
        ).inc()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": error_message,
                "error_type": error_type,
                "worker_id": settings.worker_id,
                "request_id": request_id,
            },
        )


@router.get("/healthz", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.
    
    Returns 200 if service is alive.
    """
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
    
    Returns 200 if service is ready to accept traffic.
    Checks:
    - Model loaded
    - Redis available (non-blocking)
    - Database available (non-blocking)
    """
    checks = {
        "model_loaded": await inference_service.health_check(),
        "redis_available": await redis_service.health_check(),
        "database_available": await database_service.health_check(),
    }
    
    ready = checks["model_loaded"]  # Only model is required
    
    return ReadinessResponse(
        ready=ready,
        worker_id=settings.worker_id,
        checks=checks,
        timestamp=datetime.utcnow(),
    )


@router.get("/metrics")
async def metrics() -> Response:
    """
    Prometheus metrics endpoint.
    
    Returns metrics in Prometheus format.
    """
    # Update memory metrics
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    memory_usage_bytes.labels(worker_id=settings.worker_id).set(memory_info.rss)
    
    # Update database pool metrics
    database_service.update_pool_metrics()
    
    # Generate metrics
    metrics_output = generate_latest()
    
    return Response(
        content=metrics_output,
        media_type=CONTENT_TYPE_LATEST,
    )
