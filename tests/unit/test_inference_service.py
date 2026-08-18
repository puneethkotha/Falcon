"""Tests for the streaming LLM inference service (mocked engine, no network)."""
import httpx
import pytest

from app.services.inference_service import InferenceService, GenerationResult


SSE_BODY = (
    b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
    b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
    b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],'
    b'"usage":{"prompt_tokens":3,"completion_tokens":2}}\n\n'
    b"data: [DONE]\n\n"
)


def _service_with(handler) -> InferenceService:
    svc = InferenceService()
    svc._client = httpx.AsyncClient(
        base_url="http://engine/v1", transport=httpx.MockTransport(handler)
    )
    svc.model_loaded = True
    return svc


async def test_stream_yields_sse_frames_and_records_result():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(200, content=SSE_BODY, headers={"content-type": "text/event-stream"})

    svc = _service_with(handler)
    result = GenerationResult()
    frames = [f async for f in svc.stream([{"role": "user", "content": "hi"}], result=result)]

    # Frames are valid SSE and include the DONE sentinel, passed through unchanged.
    assert any(f.startswith("data:") for f in frames)
    assert frames[-1] == "data: [DONE]\n\n"
    # Aggregated result is populated from the stream.
    assert result.text == "Hello world"
    assert result.completion_tokens == 2
    assert result.prompt_tokens == 3
    assert result.finish_reason == "stop"
    assert result.ttft_ms is not None and result.ttft_ms >= 0
    assert result.generation_ms is not None
    await svc.aclose()


async def test_generate_text_collects_full_output():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=SSE_BODY)

    svc = _service_with(handler)
    text, result = await svc.generate_text([{"role": "user", "content": "hi"}])
    assert text == "Hello world"
    assert result.completion_tokens == 2
    await svc.aclose()


async def test_classify_maps_label(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        body = (
            b'data: {"choices":[{"delta":{"content":"positive"}}]}\n\n'
            b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            b"data: [DONE]\n\n"
        )
        return httpx.Response(200, content=body)

    svc = _service_with(handler)
    label, confidence, probs = await svc.classify("this is great")
    assert label == "positive"
    assert probs["positive"] == 1.0
    assert probs["negative"] == 0.0
    assert 0.0 <= confidence <= 1.0
    await svc.aclose()


async def test_breaker_opens_on_engine_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("engine down", request=request)

    svc = _service_with(handler)
    from app.utils.circuit_breaker import CircuitBreakerState, CircuitBreakerOpenError

    # Drive failures up to the threshold; each request is one breaker failure.
    for _ in range(svc.vllm_breaker.failure_threshold):
        with pytest.raises(Exception):
            async for _f in svc.stream([{"role": "user", "content": "hi"}]):
                pass

    assert svc.vllm_breaker.state == CircuitBreakerState.OPEN
    # Next call is rejected fast by the open breaker.
    with pytest.raises(CircuitBreakerOpenError):
        async for _f in svc.stream([{"role": "user", "content": "hi"}]):
            pass
    await svc.aclose()


def test_map_label_variants():
    svc = InferenceService()
    assert svc._map_label("positive") == "positive"
    assert svc._map_label("NEGATIVE\n") == "negative"
    assert svc._map_label("neutral.") == "neutral"
    assert svc._map_label("this looks good") == "positive"
    assert svc._map_label("unparseable") == "neutral"


def test_payload_sets_stream_options():
    svc = InferenceService()
    payload = svc._payload([{"role": "user", "content": "hi"}], {"max_tokens": 5}, stream=True)
    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}
    assert payload["max_tokens"] == 5
