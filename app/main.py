"""Main FastAPI application."""
import asyncio
import signal
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.metrics import init_metrics
from app.api.routes import router
from app.middleware.request_id import RequestIDMiddleware
from app.services.redis_service import redis_service
from app.services.database_service import database_service
from app.services.inference_service import inference_service

# Setup logging first
setup_logging()
logger = get_logger(__name__)

# Track graceful shutdown
_shutdown_event = asyncio.Event()
_accepting_requests = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info(
        "Starting Falcon ML Inference Platform",
        extra={
            "worker_id": settings.worker_id,
            "environment": settings.environment,
            "version": settings.app_version,
        },
    )
    
    # Initialize metrics
    init_metrics(
        worker_id=settings.worker_id,
        app_name=settings.app_name,
        version=settings.app_version,
    )
    
    # Connect to services
    try:
        logger.info("Connecting to Redis...")
        await redis_service.connect()
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        logger.warning("Continuing without Redis (cache and idempotency disabled)")
    
    try:
        logger.info("Connecting to database...")
        await database_service.connect()
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        logger.warning("Continuing without database (logging will be buffered)")
    
    # Load ML model
    try:
        logger.info("Loading ML model...")
        await inference_service.load_model()
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise
    
    # Setup signal handlers for graceful shutdown
    def handle_shutdown_signal(signum, frame):
        """Handle shutdown signals."""
        logger.info(
            f"Received signal {signum}, initiating graceful shutdown",
            extra={"signal": signum},
        )
        _shutdown_event.set()
    
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Starting graceful shutdown...")
    
    # Stop accepting new requests
    global _accepting_requests
    _accepting_requests = False
    
    # Wait for in-flight requests with timeout
    shutdown_timeout = settings.graceful_shutdown_timeout_seconds
    logger.info(f"Waiting up to {shutdown_timeout}s for in-flight requests...")
    
    try:
        await asyncio.wait_for(
            asyncio.sleep(2),  # Give requests time to complete
            timeout=shutdown_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Graceful shutdown timeout exceeded")
    
    # Flush any buffered logs
    try:
        flushed = await database_service.flush_log_buffer()
        if flushed > 0:
            logger.info(f"Flushed {flushed} buffered logs")
    except Exception as e:
        logger.error(f"Failed to flush logs: {e}")
    
    # Disconnect from services
    try:
        await redis_service.disconnect()
    except Exception as e:
        logger.error(f"Error disconnecting from Redis: {e}")
    
    try:
        await database_service.disconnect()
    except Exception as e:
        logger.error(f"Error disconnecting from database: {e}")
    
    logger.info("Graceful shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Production-grade ML inference platform with observability and reliability features",
    lifespan=lifespan,
)

# Add middleware
app.add_middleware(RequestIDMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "worker_id": settings.worker_id,
        "status": "running" if _accepting_requests else "shutting_down",
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_config=None,  # Use our custom logging
    )
