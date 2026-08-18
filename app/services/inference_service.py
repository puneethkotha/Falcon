"""LLM inference service.

Falcon's payload used to be an in-process sklearn classifier. It now proxies an
OpenAI-compatible vLLM engine, streaming tokens back to the caller while recording
token-level timings (TTFT, inter-token latency, output tokens). The vLLM engine is
treated as one more protected dependency: the same CircuitBreaker and retry_with_backoff
constructs that already guard Redis and Postgres guard the engine here.
"""
import json
import time
import logging
from typing import AsyncIterator, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.metrics import (
    model_load_duration_seconds,
    falcon_ttft_seconds,
    falcon_inter_token_seconds,
    falcon_generation_duration_seconds,
    falcon_output_tokens_total,
    falcon_prompt_tokens_total,
)
from app.utils.circuit_breaker import CircuitBreaker
from app.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class GenerationResult:
    """Aggregated result of a streamed generation, used for logging and quality sampling."""

    __slots__ = ("text", "ttft_ms", "generation_ms", "prompt_tokens", "completion_tokens", "finish_reason")

    def __init__(self) -> None:
        self.text: str = ""
        self.ttft_ms: Optional[float] = None
        self.generation_ms: Optional[float] = None
        self.prompt_tokens: Optional[int] = None
        self.completion_tokens: Optional[int] = None
        self.finish_reason: Optional[str] = None


class InferenceService:
    """Streaming LLM inference service backed by an OpenAI-compatible engine."""

    def __init__(self) -> None:
        self.base_url = settings.vllm_base_url.rstrip("/")
        self.model_id = settings.model_id
        self.label_names = ["negative", "neutral", "positive"]
        self.model_loaded = False
        self.engine_ready = False
        self._client: Optional[httpx.AsyncClient] = None
        # The engine is a protected dependency, exactly like Redis and Postgres.
        self.vllm_breaker = CircuitBreaker(
            dependency_name="vllm",
            failure_threshold=settings.circuit_breaker_failure_threshold,
            timeout_seconds=settings.circuit_breaker_timeout_seconds,
            half_open_attempts=settings.circuit_breaker_half_open_attempts,
        )

    async def load_model(self) -> None:
        """Create the engine client and probe its health.

        This is tolerant by design: if the engine is cold or unreachable at
        startup, the worker still boots (like Redis/Postgres). The circuit
        breaker then manages the dependency at request time.
        """
        start_time = time.time()
        timeout = httpx.Timeout(
            settings.generation_timeout_seconds,
            connect=settings.generation_connect_timeout_seconds,
        )
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {settings.vllm_api_key}"},
        )
        self.model_loaded = True  # client is ready to attempt calls

        try:
            resp = await self._client.get("/models")
            self.engine_ready = resp.status_code == 200
            if self.engine_ready:
                logger.info(
                    "Connected to LLM engine",
                    extra={"base_url": self.base_url, "model_id": self.model_id},
                )
            else:
                logger.warning(
                    "LLM engine probe returned non-200",
                    extra={"status_code": resp.status_code, "base_url": self.base_url},
                )
        except Exception as e:
            self.engine_ready = False
            logger.warning(
                "LLM engine unreachable at startup; breaker will manage it",
                extra={"error": str(e), "base_url": self.base_url},
            )

        model_load_duration_seconds.labels(worker_id=settings.worker_id).set(
            time.time() - start_time
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _payload(
        self,
        messages: List[Dict[str, str]],
        params: Dict,
        stream: bool,
    ) -> Dict:
        payload = {
            "model": self.model_id,
            "messages": messages,
            "stream": stream,
            "max_tokens": params.get("max_tokens", settings.default_max_tokens),
            "temperature": params.get("temperature", settings.default_temperature),
        }
        for key in ("top_p", "top_k", "stop", "presence_penalty", "frequency_penalty"):
            if key in params and params[key] is not None:
                payload[key] = params[key]
        if stream:
            # Ask the engine to emit a final usage chunk so token economics are exact.
            payload["stream_options"] = {"include_usage": True}
        return payload

    async def stream(
        self,
        messages: List[Dict[str, str]],
        params: Optional[Dict] = None,
        result: Optional[GenerationResult] = None,
    ) -> AsyncIterator[str]:
        """Stream an OpenAI-compatible completion, yielding SSE frames unchanged.

        Yields strings that are already valid Server-Sent-Events frames
        ("data: {json}\\n\\n"), so any OpenAI-compatible client works unmodified.
        Records TTFT / inter-token latency / token counts as chunks arrive.

        The network-risky phase (connect + response headers) is wrapped by the
        vLLM circuit breaker and retry; a cold/dead engine opens the breaker and
        surfaces as a structured error rather than a hang.
        """
        if self._client is None:
            raise RuntimeError("Inference engine client not initialized")

        params = params or {}
        payload = self._payload(messages, params, stream=True)
        result = result if result is not None else GenerationResult()

        t0 = time.perf_counter()

        async def _open() -> Tuple[httpx.Response, "httpx._client.AsyncClient"]:
            cm = self._client.stream("POST", "/chat/completions", json=payload)
            response = await cm.__aenter__()
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", "replace")[:500]
                await cm.__aexit__(None, None, None)
                raise httpx.HTTPStatusError(
                    f"engine returned {response.status_code}: {body}",
                    request=response.request,
                    response=response,
                )
            return response, cm

        # Breaker + retry guard the connect/headers phase only, so a dead engine
        # opens the breaker fast; streaming iteration happens outside the gate.
        # NOTE: CircuitBreaker.call expects a zero-arg callable, so retry_with_backoff
        # is wrapped in a lambda (it returns a coroutine, which is not itself callable).
        response, cm = await self.vllm_breaker.call(
            lambda: retry_with_backoff(
                _open,
                operation_name="vllm_generate",
                exceptions=(httpx.TransportError, httpx.TimeoutException),
            )
        )

        first = True
        last = t0
        content_chunks = 0
        try:
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    yield "data: [DONE]\n\n"
                    break

                now = time.perf_counter()
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    yield f"data: {data}\n\n"
                    continue

                delta_text = self._extract_delta(obj)
                usage = obj.get("usage")
                if usage:
                    result.prompt_tokens = usage.get("prompt_tokens")
                    result.completion_tokens = usage.get("completion_tokens")
                finish = self._extract_finish(obj)
                if finish:
                    result.finish_reason = finish

                if delta_text:
                    if first:
                        ttft = now - t0
                        falcon_ttft_seconds.labels(settings.worker_id).observe(ttft)
                        result.ttft_ms = ttft * 1000.0
                        first = False
                    else:
                        falcon_inter_token_seconds.labels(settings.worker_id).observe(
                            now - last
                        )
                    last = now
                    content_chunks += 1
                    result.text += delta_text

                yield f"data: {data}\n\n"
        finally:
            await cm.__aexit__(None, None, None)

        total = time.perf_counter() - t0
        result.generation_ms = total * 1000.0
        falcon_generation_duration_seconds.labels(settings.worker_id).observe(total)

        completion_tokens = result.completion_tokens or content_chunks
        if completion_tokens:
            falcon_output_tokens_total.labels(settings.worker_id).inc(completion_tokens)
            result.completion_tokens = completion_tokens
        if result.prompt_tokens:
            falcon_prompt_tokens_total.labels(settings.worker_id).inc(result.prompt_tokens)

    @staticmethod
    def _extract_delta(obj: Dict) -> str:
        choices = obj.get("choices") or []
        if not choices:
            return ""
        delta = choices[0].get("delta") or {}
        return delta.get("content") or ""

    @staticmethod
    def _extract_finish(obj: Dict) -> Optional[str]:
        choices = obj.get("choices") or []
        if not choices:
            return None
        return choices[0].get("finish_reason")

    async def generate_text(
        self,
        messages: List[Dict[str, str]],
        params: Optional[Dict] = None,
    ) -> Tuple[str, GenerationResult]:
        """Collect a full (non-streamed-to-client) generation by consuming the stream.

        Reuses the streaming path so timings and token accounting are identical.
        """
        result = GenerationResult()
        async for _ in self.stream(messages, params, result=result):
            pass
        return result.text, result

    async def classify(self, text: str) -> Tuple[str, float, Dict[str, float]]:
        """Backward-compatible sentiment classify, re-expressed as a constrained LLM call.

        Keeps /infer, the k6 baseline, and the legacy demo working during migration.
        Uses a fixed system prompt + tiny max_tokens and maps the label back to the
        original 3-class response schema.
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a sentiment classifier. Reply with exactly one word: "
                    "negative, neutral, or positive. No punctuation, no explanation."
                ),
            },
            {"role": "user", "content": text},
        ]
        params = {
            "max_tokens": settings.classify_max_tokens,
            "temperature": settings.classify_temperature,
        }
        raw, _ = await self.generate_text(messages, params)
        label = self._map_label(raw)
        # A single constrained call does not yield calibrated probabilities; report a
        # deterministic one-hot with the chosen label at high confidence. The value of
        # this path is API compatibility, not probability quality (see docs/TRADEOFFS.md).
        probs = {name: 0.0 for name in self.label_names}
        probs[label] = 1.0
        return label, 1.0, probs

    def _map_label(self, raw: str) -> str:
        text = (raw or "").strip().lower()
        for name in self.label_names:
            if name in text:
                return name
        # Heuristic fallback if the model emitted something off-spec.
        if any(w in text for w in ("pos", "good", "great")):
            return "positive"
        if any(w in text for w in ("neg", "bad", "poor")):
            return "negative"
        return "neutral"

    def _metrics_url(self) -> str:
        base = self.base_url
        if base.endswith("/v1"):
            base = base[:-3]
        return base.rstrip("/") + "/metrics"

    async def serving_stats(self) -> Dict:
        """Best-effort snapshot of engine serving stats for the demo observability pane.

        Parses a few vllm:* series from the engine's /metrics so the frontend can read
        them same-origin (no CORS) and they work for real vLLM and the mock alike.
        """
        if self._client is None:
            return {}
        try:
            resp = await self._client.get(self._metrics_url())
            text = resp.text
        except Exception:
            return {}

        import re

        def _v(name: str) -> Optional[float]:
            m = re.search(rf"^{re.escape(name)}(?:\{{[^}}]*\}})?\s+([0-9eE.+-]+)", text, re.M)
            return float(m.group(1)) if m else None

        kv = _v("vllm:gpu_cache_usage_perc")
        if kv is None:
            kv = _v("vllm:kv_cache_usage_perc")
        hits = _v("vllm:prefix_cache_hits_total")
        queries = _v("vllm:prefix_cache_queries_total")
        prefix_hit = (hits / queries) if (hits is not None and queries) else None
        return {
            "kv_cache_pct": round(kv * 100, 1) if kv is not None else None,
            "running": _v("vllm:num_requests_running"),
            "waiting": _v("vllm:num_requests_waiting"),
            "prefix_hit_rate": round(prefix_hit, 3) if prefix_hit is not None else None,
        }

    async def health_check(self) -> bool:
        """Service is healthy if the engine client exists (breaker manages the engine)."""
        return self.model_loaded

    async def engine_probe(self) -> bool:
        """Live probe of the engine, used by readiness."""
        if self._client is None:
            return False
        try:
            resp = await self._client.get("/models")
            self.engine_ready = resp.status_code == 200
        except Exception:
            self.engine_ready = False
        return self.engine_ready


# Global instance
inference_service = InferenceService()
