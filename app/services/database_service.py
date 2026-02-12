"""Database service for logging inference requests."""
import asyncio
import logging
from collections import deque
from typing import Optional, Dict, Any, Deque
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy import select, func

from app.core.config import settings
from app.models.database import Base, InferenceLog
from app.core.metrics import (
    db_operations_total,
    db_operation_duration_seconds,
    db_connection_pool_size,
    db_connection_pool_available,
    dropped_logs_total,
    fallback_triggered_total,
)
from app.utils.circuit_breaker import CircuitBreaker
from app.utils.retry import retry_with_backoff
import time

logger = logging.getLogger(__name__)


class DatabaseService:
    """Database service with circuit breaker, retry logic, and fallback buffer."""

    def __init__(self):
        """Initialize database service."""
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker] = None
        self.circuit_breaker = CircuitBreaker(
            dependency_name="postgres",
            failure_threshold=settings.circuit_breaker_failure_threshold,
            timeout_seconds=settings.circuit_breaker_timeout_seconds,
            half_open_attempts=settings.circuit_breaker_half_open_attempts,
        )
        
        # Fallback buffer for logs when DB is down
        self.log_buffer: Deque[Dict[str, Any]] = deque(maxlen=1000)
        self.buffer_enabled = False

    async def connect(self) -> None:
        """Connect to database and create tables."""
        try:
            self.engine = create_async_engine(
                settings.async_database_url,
                pool_size=settings.postgres_pool_size,
                max_overflow=settings.postgres_max_overflow,
                pool_timeout=settings.postgres_pool_timeout,
                pool_recycle=settings.postgres_pool_recycle,
                echo=False,
            )
            
            self.session_factory = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            
            # Create tables
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            logger.info("Connected to database successfully")
            
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def disconnect(self) -> None:
        """Disconnect from database."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Disconnected from database")

    @asynccontextmanager
    async def get_session(self):
        """Get database session context manager."""
        if not self.session_factory:
            raise RuntimeError("Database not connected")
        
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def log_inference_request(
        self,
        request_id: str,
        text_hash: str,
        text_length: int,
        prediction: Optional[str] = None,
        confidence: Optional[float] = None,
        probabilities: Optional[Dict[str, float]] = None,
        cache_hit: bool = False,
        idempotency_hit: bool = False,
        success: bool = True,
        processing_time_ms: Optional[float] = None,
        inference_time_ms: Optional[float] = None,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        client_ip: Optional[str] = None,
    ) -> bool:
        """
        Log inference request to database with fallback to buffer.
        
        Returns True if logged successfully, False if buffered/dropped.
        """
        log_data = {
            "request_id": request_id,
            "worker_id": settings.worker_id,
            "text_hash": text_hash,
            "text_length": text_length,
            "prediction": prediction,
            "confidence": confidence,
            "probabilities": probabilities,
            "cache_hit": cache_hit,
            "idempotency_hit": idempotency_hit,
            "success": success,
            "processing_time_ms": processing_time_ms,
            "inference_time_ms": inference_time_ms,
            "error_type": error_type,
            "error_message": error_message,
            "idempotency_key": idempotency_key,
            "client_ip": client_ip,
        }

        try:
            start_time = time.time()

            async def _log():
                async with self.get_session() as session:
                    log_entry = InferenceLog(**log_data)
                    session.add(log_entry)
                    await session.flush()
                return True

            async def _fallback():
                logger.warning("Database unavailable, buffering log entry")
                fallback_triggered_total.labels(
                    worker_id=settings.worker_id,
                    dependency="postgres",
                    fallback_type="buffer_log",
                ).inc()
                
                # Add to buffer
                if len(self.log_buffer) >= self.log_buffer.maxlen:
                    dropped_logs_total.labels(worker_id=settings.worker_id).inc()
                    logger.error("Log buffer full, dropping oldest entry")
                
                self.log_buffer.append(log_data)
                self.buffer_enabled = True
                return False

            result = await self.circuit_breaker.call(
                retry_with_backoff(
                    _log,
                    operation_name="db_log_inference",
                    exceptions=(OperationalError, SQLAlchemyError),
                ),
                fallback=_fallback,
            )

            duration = time.time() - start_time
            
            db_operations_total.labels(
                worker_id=settings.worker_id,
                operation="log_inference",
                status="success" if result else "fallback",
            ).inc()
            
            db_operation_duration_seconds.labels(
                worker_id=settings.worker_id,
                operation="log_inference",
            ).observe(duration)
            
            return result

        except Exception as e:
            logger.error(f"Failed to log inference request: {e}")
            db_operations_total.labels(
                worker_id=settings.worker_id,
                operation="log_inference",
                status="error",
            ).inc()
            return False

    async def flush_log_buffer(self) -> int:
        """
        Flush buffered logs to database.
        
        Returns number of logs successfully flushed.
        """
        if not self.buffer_enabled or not self.log_buffer:
            return 0

        flushed_count = 0
        failed_logs = []

        logger.info(f"Flushing {len(self.log_buffer)} buffered logs")

        while self.log_buffer:
            log_data = self.log_buffer.popleft()
            try:
                async with self.get_session() as session:
                    log_entry = InferenceLog(**log_data)
                    session.add(log_entry)
                    await session.flush()
                flushed_count += 1
            except Exception as e:
                logger.error(f"Failed to flush log: {e}")
                failed_logs.append(log_data)

        # Re-add failed logs to buffer
        for log_data in failed_logs:
            self.log_buffer.append(log_data)

        if not self.log_buffer:
            self.buffer_enabled = False

        logger.info(
            f"Flushed {flushed_count} logs, {len(failed_logs)} failed",
            extra={
                "flushed": flushed_count,
                "failed": len(failed_logs),
                "remaining": len(self.log_buffer),
            },
        )

        return flushed_count

    async def get_recent_stats(self, limit: int = 100) -> Dict[str, Any]:
        """Get recent inference statistics."""
        try:
            async with self.get_session() as session:
                # Total requests
                total_result = await session.execute(
                    select(func.count(InferenceLog.id))
                )
                total = total_result.scalar()

                # Success rate
                success_result = await session.execute(
                    select(func.count(InferenceLog.id)).where(
                        InferenceLog.success == True
                    )
                )
                success_count = success_result.scalar()

                # Cache hit rate
                cache_hit_result = await session.execute(
                    select(func.count(InferenceLog.id)).where(
                        InferenceLog.cache_hit == True
                    )
                )
                cache_hits = cache_hit_result.scalar()

                # Average processing time
                avg_time_result = await session.execute(
                    select(func.avg(InferenceLog.processing_time_ms))
                )
                avg_time = avg_time_result.scalar()

                return {
                    "total_requests": total or 0,
                    "success_count": success_count or 0,
                    "success_rate": (success_count / total) if total else 0,
                    "cache_hits": cache_hits or 0,
                    "cache_hit_rate": (cache_hits / total) if total else 0,
                    "avg_processing_time_ms": float(avg_time) if avg_time else 0,
                }

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}

    async def health_check(self) -> bool:
        """Check if database is healthy."""
        if not self.engine:
            return False

        try:
            async with self.engine.connect() as conn:
                await conn.execute(select(1))
            return True
        except Exception:
            return False

    def update_pool_metrics(self) -> None:
        """Update connection pool metrics."""
        if not self.engine or not self.engine.pool:
            return

        try:
            pool = self.engine.pool
            db_connection_pool_size.labels(worker_id=settings.worker_id).set(
                pool.size()
            )
            # Note: Not all pools expose available connections
            # This is a best-effort metric
        except Exception as e:
            logger.debug(f"Could not update pool metrics: {e}")


# Global instance
database_service = DatabaseService()
