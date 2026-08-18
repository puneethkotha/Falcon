"""Add LLM token-economics columns to inference_logs and the quality_scores table.

Revision ID: 0001_llm_token_columns
Revises:
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_llm_token_columns"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Token economics on the existing request log.
    op.add_column("inference_logs", sa.Column("model_id", sa.String(length=128), nullable=True))
    op.add_column("inference_logs", sa.Column("prompt_tokens", sa.Integer(), nullable=True))
    op.add_column("inference_logs", sa.Column("completion_tokens", sa.Integer(), nullable=True))
    op.add_column("inference_logs", sa.Column("ttft_ms", sa.Float(), nullable=True))
    op.add_column("inference_logs", sa.Column("generation_ms", sa.Float(), nullable=True))

    # Online quality-observability scores.
    op.create_table(
        "quality_scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("worker_id", sa.String(length=64), nullable=False),
        sa.Column("path", sa.String(length=32), nullable=False),
        sa.Column("check_passed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("failed_checks", sa.JSON(), nullable=True),
        sa.Column("refusal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("output_length", sa.Integer(), nullable=True),
        sa.Column("judge_score", sa.Float(), nullable=True),
        sa.Column("judge_model", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_quality_scores_request_id", "quality_scores", ["request_id"])
    op.create_index("ix_quality_scores_worker_id", "quality_scores", ["worker_id"])
    op.create_index("ix_quality_scores_created_at", "quality_scores", ["created_at"])
    op.create_index("idx_quality_worker_created", "quality_scores", ["worker_id", "created_at"])
    op.create_index("idx_quality_refusal_created", "quality_scores", ["refusal", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_quality_refusal_created", table_name="quality_scores")
    op.drop_index("idx_quality_worker_created", table_name="quality_scores")
    op.drop_index("ix_quality_scores_created_at", table_name="quality_scores")
    op.drop_index("ix_quality_scores_worker_id", table_name="quality_scores")
    op.drop_index("ix_quality_scores_request_id", table_name="quality_scores")
    op.drop_table("quality_scores")

    op.drop_column("inference_logs", "generation_ms")
    op.drop_column("inference_logs", "ttft_ms")
    op.drop_column("inference_logs", "completion_tokens")
    op.drop_column("inference_logs", "prompt_tokens")
    op.drop_column("inference_logs", "model_id")
