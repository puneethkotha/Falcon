"""Test circuit breaker functionality."""
import pytest
import asyncio
from app.utils.circuit_breaker import CircuitBreaker, CircuitBreakerState, CircuitBreakerOpenError


@pytest.mark.asyncio
async def test_circuit_breaker_closed_state():
    """Test circuit breaker starts in closed state."""
    cb = CircuitBreaker(
        dependency_name="test",
        failure_threshold=3,
        timeout_seconds=5,
        half_open_attempts=2,
    )
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold():
    """Test circuit breaker opens after failure threshold."""
    cb = CircuitBreaker(
        dependency_name="test",
        failure_threshold=3,
        timeout_seconds=5,
        half_open_attempts=2,
    )
    
    async def failing_func():
        raise Exception("Test failure")
    
    # Trigger failures
    for _ in range(3):
        with pytest.raises(Exception):
            await cb.call(failing_func)
    
    # Circuit should be open now
    assert cb.state == CircuitBreakerState.OPEN
    assert cb.failure_count == 3


@pytest.mark.asyncio
async def test_circuit_breaker_fallback():
    """Test circuit breaker calls fallback when open."""
    cb = CircuitBreaker(
        dependency_name="test",
        failure_threshold=2,
        timeout_seconds=5,
        half_open_attempts=2,
    )
    
    async def failing_func():
        raise Exception("Test failure")
    
    async def fallback():
        return "fallback_result"
    
    # Trigger failures to open circuit
    for _ in range(2):
        with pytest.raises(Exception):
            await cb.call(failing_func)
    
    # Now circuit is open, should use fallback
    result = await cb.call(failing_func, fallback=fallback)
    assert result == "fallback_result"


@pytest.mark.asyncio
async def test_circuit_breaker_success():
    """Test circuit breaker with successful calls."""
    cb = CircuitBreaker(
        dependency_name="test",
        failure_threshold=3,
        timeout_seconds=5,
        half_open_attempts=2,
    )
    
    async def successful_func():
        return "success"
    
    result = await cb.call(successful_func)
    assert result == "success"
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_recovery():
    """Test circuit breaker transitions to half-open and recovers."""
    cb = CircuitBreaker(
        dependency_name="test",
        failure_threshold=2,
        timeout_seconds=1,  # Short timeout for test
        half_open_attempts=2,
    )
    
    async def failing_func():
        raise Exception("Test failure")
    
    async def successful_func():
        return "success"
    
    # Open the circuit
    for _ in range(2):
        with pytest.raises(Exception):
            await cb.call(failing_func)
    
    assert cb.state == CircuitBreakerState.OPEN
    
    # Wait for timeout
    await asyncio.sleep(1.5)
    
    # Next call should transition to half-open
    result = await cb.call(successful_func)
    assert result == "success"
    
    # After enough successes, should close
    for _ in range(1):
        await cb.call(successful_func)
    
    assert cb.state == CircuitBreakerState.CLOSED
