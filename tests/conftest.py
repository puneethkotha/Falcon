"""Pytest configuration."""
import pytest
from app.core.config import Settings


@pytest.fixture
def test_settings():
    """Create test settings."""
    return Settings(
        environment="test",
        redis_host="localhost",
        postgres_host="localhost",
        circuit_breaker_enabled=True,
        retry_enabled=True,
        cache_enabled=True,
        idempotency_enabled=True,
    )


@pytest.fixture
def sample_inference_text():
    """Sample text for inference testing."""
    return "This is a great product!"


@pytest.fixture
def sample_predictions():
    """Sample prediction results."""
    return {
        "prediction": "positive",
        "confidence": 0.95,
        "probabilities": {
            "negative": 0.02,
            "neutral": 0.03,
            "positive": 0.95,
        },
    }
