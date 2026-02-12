"""Retry logic with exponential backoff."""
import asyncio
import logging
from typing import Callable, Any, Type, Tuple, Optional

from app.core.config import settings
from app.core.metrics import retry_attempts_total

logger = logging.getLogger(__name__)


async def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    operation_name: str = "operation",
    max_attempts: Optional[int] = None,
    base_delay_ms: Optional[int] = None,
    max_delay_ms: Optional[int] = None,
    exponential_base: Optional[int] = None,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    **kwargs: Any,
) -> Any:
    """
    Retry function with exponential backoff.
    
    Args:
        func: Async function to retry
        operation_name: Name for logging and metrics
        max_attempts: Maximum retry attempts (default from settings)
        base_delay_ms: Base delay in milliseconds (default from settings)
        max_delay_ms: Maximum delay in milliseconds (default from settings)
        exponential_base: Exponential backoff base (default from settings)
        exceptions: Tuple of exceptions to catch and retry
        *args, **kwargs: Arguments to pass to func
    """
    if not settings.retry_enabled:
        return await func(*args, **kwargs)

    max_attempts = max_attempts or settings.retry_max_attempts
    base_delay_ms = base_delay_ms or settings.retry_base_delay_ms
    max_delay_ms = max_delay_ms or settings.retry_max_delay_ms
    exponential_base = exponential_base or settings.retry_exponential_base

    last_exception: Optional[Exception] = None
    
    for attempt in range(max_attempts):
        try:
            result = await func(*args, **kwargs)
            
            if attempt > 0:
                logger.info(
                    f"Retry succeeded for {operation_name}",
                    extra={
                        "operation": operation_name,
                        "attempt": attempt + 1,
                        "max_attempts": max_attempts,
                    },
                )
            
            return result
            
        except exceptions as e:
            last_exception = e
            
            if attempt < max_attempts - 1:
                # Calculate delay with exponential backoff
                delay_ms = min(
                    base_delay_ms * (exponential_base ** attempt),
                    max_delay_ms,
                )
                delay_seconds = delay_ms / 1000.0
                
                logger.warning(
                    f"Retry attempt {attempt + 1}/{max_attempts} for {operation_name}",
                    extra={
                        "operation": operation_name,
                        "attempt": attempt + 1,
                        "max_attempts": max_attempts,
                        "delay_seconds": delay_seconds,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                
                retry_attempts_total.labels(
                    worker_id=settings.worker_id,
                    operation=operation_name,
                ).inc()
                
                await asyncio.sleep(delay_seconds)
            else:
                logger.error(
                    f"All retry attempts exhausted for {operation_name}",
                    extra={
                        "operation": operation_name,
                        "max_attempts": max_attempts,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )

    # All retries exhausted
    if last_exception:
        raise last_exception
    
    # This should never happen, but just in case
    raise RuntimeError(f"Retry logic failed for {operation_name}")
