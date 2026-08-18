"""Online quality-observability sidecar.

"200 OK" is not "the output was correct." This service samples a small fraction
of completions, scores them OFF the critical path (never synchronously, so a slow
judge cannot add serving latency), and trends quality / refusal / drift.

Design:
- Async, in-process consumer fed by a bounded asyncio.Queue. A full queue drops
  samples (counted) rather than blocking the request path.
- Cheap deterministic checks first (free, catch most regressions): refusal-phrase
  detection, empty/truncated output, length hits, schema/label validity for classify.
- Optional LLM-as-judge second: a noisy estimator, disabled unless a budget is set.
  Calibrate against human labels and trend the score; never gate on a single verdict.
"""
import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.core.config import settings
from app.core.metrics import (
    falcon_quality_sampled_total,
    falcon_quality_check_failed_total,
    falcon_refusal_total,
    falcon_quality_dropped_total,
    falcon_judge_score,
)

logger = logging.getLogger(__name__)


@dataclass
class QualitySample:
    request_id: str
    path: str  # "generate" or "classify"
    prompt: str
    output: str
    finish_reason: Optional[str] = None
    label: Optional[str] = None
    confidence: Optional[float] = None
    allowed_labels: List[str] = field(default_factory=list)


class QualityService:
    """Async sampler -> deterministic checks -> optional judge -> Postgres + metrics."""

    def __init__(self) -> None:
        self._queue: "asyncio.Queue[QualitySample]" = asyncio.Queue(
            maxsize=settings.quality_queue_maxsize
        )
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._refusal_markers = [
            m.strip().lower()
            for m in settings.quality_refusal_markers.split(",")
            if m.strip()
        ]

    def should_sample(self) -> bool:
        return (
            settings.quality_sampling_enabled
            and random.random() < settings.quality_sample_rate
        )

    def submit(self, sample: QualitySample) -> None:
        """Non-blocking enqueue; drop (and count) if the queue is full."""
        try:
            self._queue.put_nowait(sample)
            falcon_quality_sampled_total.labels(
                worker_id=settings.worker_id, path=sample.path
            ).inc()
        except asyncio.QueueFull:
            falcon_quality_dropped_total.labels(worker_id=settings.worker_id).inc()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._consume())
        logger.info("Quality sidecar started", extra={"sample_rate": settings.quality_sample_rate})

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _consume(self) -> None:
        # Import here to avoid a circular import at module load.
        from app.services.database_service import database_service

        while self._running:
            try:
                sample = await self._queue.get()
            except asyncio.CancelledError:
                break
            try:
                await self._score(sample, database_service)
            except Exception as e:  # never let a bad sample kill the consumer
                logger.error(f"Quality scoring failed: {e}")
            finally:
                self._queue.task_done()

    def run_checks(self, sample: QualitySample) -> Dict:
        """Deterministic checks. Pure function -> easy to unit test."""
        failed: List[str] = []
        text = (sample.output or "").strip()
        lowered = text.lower()

        refusal = any(marker in lowered for marker in self._refusal_markers)
        if refusal:
            failed.append("refusal")

        if not text:
            failed.append("empty_output")

        if sample.finish_reason == "length":
            failed.append("truncated")

        if sample.path == "classify":
            if sample.label not in (sample.allowed_labels or []):
                failed.append("label_out_of_set")
            if sample.confidence is not None and not (0.0 <= sample.confidence <= 1.0):
                failed.append("confidence_out_of_range")

        return {
            "check_passed": len(failed) == 0,
            "failed_checks": failed,
            "refusal": refusal,
            "output_length": len(text),
        }

    async def _score(self, sample: QualitySample, database_service) -> None:
        checks = self.run_checks(sample)

        for check in checks["failed_checks"]:
            falcon_quality_check_failed_total.labels(
                worker_id=settings.worker_id, check=check
            ).inc()
        if checks["refusal"]:
            falcon_refusal_total.labels(worker_id=settings.worker_id).inc()

        judge_score: Optional[float] = None
        judge_model: Optional[str] = None
        if settings.quality_judge_enabled:
            judge_score = await self._judge(sample)
            if judge_score is not None:
                judge_model = settings.quality_judge_model
                falcon_judge_score.labels(settings.worker_id).observe(judge_score)

        await database_service.log_quality_score(
            request_id=sample.request_id,
            path=sample.path,
            check_passed=checks["check_passed"],
            failed_checks=checks["failed_checks"] or None,
            refusal=checks["refusal"],
            output_length=checks["output_length"],
            judge_score=judge_score,
            judge_model=judge_model,
        )

    async def _judge(self, sample: QualitySample) -> Optional[float]:
        """LLM-as-judge via the same engine. Off critical path; best-effort.

        Returns a 0-1 score parsed from a rubric prompt, or None on any failure.
        Treat as a noisy estimator: calibrate with benchmarks/calibrate_judge.py and
        trend the score rather than gating on a single verdict.
        """
        from app.services.inference_service import inference_service

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a strict evaluator. Given a prompt and a response, rate the "
                    "response quality from 0.0 to 1.0. Reply with only the number."
                ),
            },
            {
                "role": "user",
                "content": f"PROMPT:\n{sample.prompt}\n\nRESPONSE:\n{sample.output}\n\nScore:",
            },
        ]
        try:
            raw, _ = await inference_service.generate_text(
                messages, {"max_tokens": 8, "temperature": 0.0}
            )
            for token in raw.replace(",", " ").split():
                try:
                    value = float(token)
                    return max(0.0, min(1.0, value))
                except ValueError:
                    continue
        except Exception as e:
            logger.warning(f"Judge call failed: {e}")
        return None


# Global instance
quality_service = QualityService()
