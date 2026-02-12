"""Redis service for caching and idempotency."""
import json
import logging
from typing import Optional, Any
import redis.asyncio as aioredis
from redis.exceptions import RedisError, ConnectionError, TimeoutError

from app.core.config import settings
from app.core.metrics import (
    cache_hits_total,
    cache_misses_total,
    cache_errors_total,
    idempotency_hits_total,
    idempotency_misses_total,
    fallback_triggered_total,
)
from app.utils.circuit_breaker import CircuitBreaker
from app.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class RedisService:
    """Redis service with circuit breaker and retry logic."""

    def __init__(self):
        """Initialize Redis service."""
        self.client: Optional[aioredis.Redis] = None
        self.circuit_breaker = CircuitBreaker(
            dependency_name="redis",
            failure_threshold=settings.circuit_breaker_failure_threshold,
            timeout_seconds=settings.circuit_breaker_timeout_seconds,
            half_open_attempts=settings.circuit_breaker_half_open_attempts,
        )

    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            self.client = await aioredis.from_url(
                f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}",
                password=settings.redis_password,
                max_connections=settings.redis_max_connections,
                socket_timeout=settings.redis_socket_timeout,
                socket_connect_timeout=settings.redis_socket_connect_timeout,
                decode_responses=True,
            )
            await self.client.ping()
            logger.info("Connected to Redis successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.client:
            await self.client.close()
            logger.info("Disconnected from Redis")

    async def get_cache(self, key: str) -> Optional[str]:
        """
        Get cached value with circuit breaker and fallback.
        
        Returns None if cache miss or Redis unavailable.
        """
        if not settings.cache_enabled or not self.client:
            return None

        try:
            async def _get() -> Optional[str]:
                result = await self.client.get(f"cache:{key}")
                return result

            async def _fallback() -> None:
                logger.warning("Redis unavailable, proceeding without cache")
                fallback_triggered_total.labels(
                    worker_id=settings.worker_id,
                    dependency="redis",
                    fallback_type="cache_miss",
                ).inc()
                return None

            result = await self.circuit_breaker.call(
                retry_with_backoff(
                    _get,
                    operation_name="redis_get_cache",
                    exceptions=(ConnectionError, TimeoutError),
                ),
                fallback=_fallback,
            )

            if result:
                cache_hits_total.labels(worker_id=settings.worker_id).inc()
                logger.debug(f"Cache hit for key: {key}")
            else:
                cache_misses_total.labels(worker_id=settings.worker_id).inc()
                logger.debug(f"Cache miss for key: {key}")

            return result

        except Exception as e:
            logger.error(f"Cache get error: {e}", extra={"key": key})
            cache_errors_total.labels(
                worker_id=settings.worker_id,
                operation="get",
            ).inc()
            return None

    async def set_cache(
        self,
        key: str,
        value: str,
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """
        Set cached value with circuit breaker and fallback.
        
        Returns False if Redis unavailable.
        """
        if not settings.cache_enabled or not self.client:
            return False

        ttl = ttl_seconds or settings.cache_ttl_seconds

        try:
            async def _set() -> bool:
                await self.client.setex(f"cache:{key}", ttl, value)
                return True

            async def _fallback() -> bool:
                logger.warning("Redis unavailable, skipping cache set")
                fallback_triggered_total.labels(
                    worker_id=settings.worker_id,
                    dependency="redis",
                    fallback_type="cache_skip",
                ).inc()
                return False

            result = await self.circuit_breaker.call(
                retry_with_backoff(
                    _set,
                    operation_name="redis_set_cache",
                    exceptions=(ConnectionError, TimeoutError),
                ),
                fallback=_fallback,
            )

            logger.debug(f"Cache set for key: {key}, ttl: {ttl}s")
            return result

        except Exception as e:
            logger.error(f"Cache set error: {e}", extra={"key": key})
            cache_errors_total.labels(
                worker_id=settings.worker_id,
                operation="set",
            ).inc()
            return False

    async def check_idempotency(self, idempotency_key: str) -> Optional[str]:
        """
        Check if request with idempotency key was already processed.
        
        Returns cached response if found, None otherwise.
        """
        if not settings.idempotency_enabled or not self.client:
            return None

        try:
            async def _get() -> Optional[str]:
                result = await self.client.get(f"idempotency:{idempotency_key}")
                return result

            async def _fallback() -> None:
                logger.warning("Redis unavailable, skipping idempotency check")
                fallback_triggered_total.labels(
                    worker_id=settings.worker_id,
                    dependency="redis",
                    fallback_type="idempotency_skip",
                ).inc()
                return None

            result = await self.circuit_breaker.call(
                retry_with_backoff(
                    _get,
                    operation_name="redis_check_idempotency",
                    exceptions=(ConnectionError, TimeoutError),
                ),
                fallback=_fallback,
            )

            if result:
                idempotency_hits_total.labels(worker_id=settings.worker_id).inc()
                logger.info(f"Idempotency hit for key: {idempotency_key}")
            else:
                idempotency_misses_total.labels(worker_id=settings.worker_id).inc()

            return result

        except Exception as e:
            logger.error(
                f"Idempotency check error: {e}",
                extra={"idempotency_key": idempotency_key},
            )
            return None

    async def store_idempotency(
        self,
        idempotency_key: str,
        response: str,
    ) -> bool:
        """Store response for idempotency key."""
        if not settings.idempotency_enabled or not self.client:
            return False

        try:
            async def _set() -> bool:
                await self.client.setex(
                    f"idempotency:{idempotency_key}",
                    settings.idempotency_ttl_seconds,
                    response,
                )
                return True

            async def _fallback() -> bool:
                logger.warning("Redis unavailable, skipping idempotency store")
                fallback_triggered_total.labels(
                    worker_id=settings.worker_id,
                    dependency="redis",
                    fallback_type="idempotency_skip",
                ).inc()
                return False

            result = await self.circuit_breaker.call(
                retry_with_backoff(
                    _set,
                    operation_name="redis_store_idempotency",
                    exceptions=(ConnectionError, TimeoutError),
                ),
                fallback=_fallback,
            )

            return result

        except Exception as e:
            logger.error(
                f"Idempotency store error: {e}",
                extra={"idempotency_key": idempotency_key},
            )
            return False

    async def health_check(self) -> bool:
        """Check if Redis is healthy."""
        if not self.client:
            return False

        try:
            await self.client.ping()
            return True
        except Exception:
            return False


# Global instance
redis_service = RedisService()
