"""Test Pydantic schemas."""
import pytest
from pydantic import ValidationError
from app.models.schemas import InferenceRequest, InferenceResponse


def test_inference_request_valid():
    """Test valid inference request."""
    request = InferenceRequest(text="This is a test")
    assert request.text == "This is a test"


def test_inference_request_empty_text_fails():
    """Test that empty text fails validation."""
    with pytest.raises(ValidationError):
        InferenceRequest(text="")


def test_inference_request_whitespace_only_fails():
    """Test that whitespace-only text fails validation."""
    with pytest.raises(ValidationError):
        InferenceRequest(text="   ")


def test_inference_request_too_long_fails():
    """Test that text exceeding max length fails."""
    with pytest.raises(ValidationError):
        InferenceRequest(text="a" * 10001)  # Max is 10000


def test_inference_request_missing_text_fails():
    """Test that missing text field fails."""
    with pytest.raises(ValidationError):
        InferenceRequest()


def test_inference_response_valid():
    """Test valid inference response."""
    response = InferenceResponse(
        prediction="positive",
        confidence=0.95,
        probabilities={"negative": 0.02, "neutral": 0.03, "positive": 0.95},
        cache_hit=False,
        worker_id="worker-1",
        processing_time_ms=45.2,
    )
    
    assert response.prediction == "positive"
    assert response.confidence == 0.95
    assert response.cache_hit is False


def test_inference_response_confidence_range():
    """Test confidence must be between 0 and 1."""
    with pytest.raises(ValidationError):
        InferenceResponse(
            prediction="positive",
            confidence=1.5,  # Invalid
            probabilities={"positive": 1.0},
            cache_hit=False,
            worker_id="worker-1",
            processing_time_ms=45.2,
        )


def test_inference_response_all_fields():
    """Test response with all optional fields."""
    response = InferenceResponse(
        prediction="positive",
        confidence=0.95,
        probabilities={"negative": 0.02, "neutral": 0.03, "positive": 0.95},
        cache_hit=True,
        worker_id="worker-2",
        processing_time_ms=12.3,
        idempotency_hit=True,
    )
    
    assert response.idempotency_hit is True
    assert response.cache_hit is True
