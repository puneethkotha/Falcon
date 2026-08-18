"""Database models."""
from datetime import datetime
from sqlalchemy import Column, String, Float, Boolean, Integer, DateTime, JSON, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class InferenceLog(Base):
    """Inference request log table."""
    
    __tablename__ = "inference_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(64), unique=True, index=True, nullable=False)
    worker_id = Column(String(64), nullable=False, index=True)
    
    # Request data
    text_hash = Column(String(64), nullable=False, index=True)
    text_length = Column(Integer, nullable=False)
    
    # Response data
    prediction = Column(String(64), nullable=True)
    confidence = Column(Float, nullable=True)
    probabilities = Column(JSON, nullable=True)
    
    # Flags
    cache_hit = Column(Boolean, default=False, nullable=False)
    idempotency_hit = Column(Boolean, default=False, nullable=False)
    success = Column(Boolean, default=True, nullable=False)
    
    # Timing
    processing_time_ms = Column(Float, nullable=True)
    inference_time_ms = Column(Float, nullable=True)

    # LLM token economics (added in the vLLM-serving upgrade)
    model_id = Column(String(128), nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    ttft_ms = Column(Float, nullable=True)
    generation_ms = Column(Float, nullable=True)

    # Error info
    error_type = Column(String(128), nullable=True)
    error_message = Column(String(512), nullable=True)
    
    # Metadata
    idempotency_key = Column(String(128), nullable=True, index=True)
    client_ip = Column(String(45), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Indexes for common queries
    __table_args__ = (
        Index("idx_worker_created", "worker_id", "created_at"),
        Index("idx_success_created", "success", "created_at"),
        Index("idx_cache_hit_created", "cache_hit", "created_at"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<InferenceLog(id={self.id}, request_id={self.request_id}, "
            f"worker_id={self.worker_id}, success={self.success})>"
        )


class QualityScore(Base):
    """Online quality-observability score for a sampled completion.

    Written asynchronously off the critical path by the quality sidecar, so a
    slow judge never adds latency to serving.
    """

    __tablename__ = "quality_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(64), index=True, nullable=False)
    worker_id = Column(String(64), nullable=False, index=True)
    path = Column(String(32), nullable=False)  # "generate" or "classify"

    # Deterministic checks (free, always run)
    check_passed = Column(Boolean, default=True, nullable=False)
    failed_checks = Column(JSON, nullable=True)
    refusal = Column(Boolean, default=False, nullable=False)
    output_length = Column(Integer, nullable=True)

    # LLM-as-judge (optional, budgeted, noisy estimator)
    judge_score = Column(Float, nullable=True)
    judge_model = Column(String(128), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("idx_quality_worker_created", "worker_id", "created_at"),
        Index("idx_quality_refusal_created", "refusal", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<QualityScore(id={self.id}, request_id={self.request_id}, "
            f"refusal={self.refusal}, judge_score={self.judge_score})>"
        )
