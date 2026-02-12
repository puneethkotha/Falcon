"""API request/response schemas."""
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator


class InferenceRequest(BaseModel):
    """Inference request model."""
    
    text: str = Field(
        ...,
        description="Text to classify",
        min_length=1,
        max_length=10000,
        example="This is a great product!",
    )
    
    @validator("text")
    def validate_text(cls, v: str) -> str:
        """Validate text is not empty after stripping."""
        if not v.strip():
            raise ValueError("Text cannot be empty")
        return v


class InferenceResponse(BaseModel):
    """Inference response model."""
    
    prediction: str = Field(..., description="Predicted class")
    confidence: float = Field(..., description="Prediction confidence", ge=0.0, le=1.0)
    probabilities: Dict[str, float] = Field(..., description="Class probabilities")
    cache_hit: bool = Field(..., description="Whether result was from cache")
    worker_id: str = Field(..., description="Worker that processed the request")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
    idempotency_hit: bool = Field(
        default=False,
        description="Whether this was a duplicate idempotent request",
    )


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str = Field(..., description="Service status")
    worker_id: str = Field(..., description="Worker identifier")
    timestamp: datetime = Field(..., description="Current timestamp")
    uptime_seconds: float = Field(..., description="Uptime in seconds")


class ReadinessResponse(BaseModel):
    """Readiness check response."""
    
    ready: bool = Field(..., description="Whether service is ready")
    worker_id: str = Field(..., description="Worker identifier")
    checks: Dict[str, bool] = Field(..., description="Individual readiness checks")
    timestamp: datetime = Field(..., description="Current timestamp")


class ErrorResponse(BaseModel):
    """Error response model."""
    
    error: str = Field(..., description="Error message")
    error_type: str = Field(..., description="Error type")
    worker_id: str = Field(..., description="Worker identifier")
    timestamp: datetime = Field(..., description="Error timestamp")
    request_id: Optional[str] = Field(None, description="Request ID if available")
