"""Add phase1_export_run, phase1_export_thread, phase1_export_category, phase1_export_keyword_hit, phase1_export_crossgen_hit.

Revision ID: 009
Revises: 008
Create Date: 2025-02-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "phase1_export_run",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("exported_at", sa.DateTime(), nullable=False),
        sa.Column("exported_decision", sa.String(16), nullable=False),
        sa.Column("exported_count", sa.Integer(), nullable=False),
        sa.Column("total_scored_rows", sa.Integer(), nullable=False),
        sa.Column("by_decision", sa.Text(), nullable=False),
        sa.Column("scoring_version_filter", sa.String(32), nullable=True),
        sa.Column("top_n", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_phase1_export_run_exported_at",
        "phase1_export_run",
        ["exported_at"],
        unique=False,
    )

    op.create_table(
        "phase1_export_thread",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("final_score", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("category_path", sa.Text(), nullable=False),
        sa.Column("is_sticky", sa.Boolean(), nullable=False),
        sa.Column("replies_no", sa.Integer(), nullable=False),
        sa.Column("pagination_no", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("last_post_at", sa.Text(), nullable=False),
        sa.Column("activity_span_years", sa.Integer(), nullable=False),
        sa.Column("revival_count", sa.Integer(), nullable=False),
        sa.Column("matched_category", sa.String(512), nullable=False),
        sa.Column("problem_keywords", sa.Text(), nullable=False),
        sa.Column("cross_gen_signals", sa.Text(), nullable=False),
        sa.Column("noise_flags", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["phase1_export_run.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_phase1_export_thread_run_id",
        "phase1_export_thread",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_phase1_export_thread_thread_id",
        "phase1_export_thread",
        ["thread_id"],
        unique=False,
    )

    op.create_table(
        "phase1_export_category",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(512), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("avg_score", sa.Float(), nullable=False),
        sa.Column("median_score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["phase1_export_run.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_phase1_export_category_run_id",
        "phase1_export_category",
        ["run_id"],
        unique=False,
    )

    op.create_table(
        "phase1_export_keyword_hit",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("keyword", sa.String(256), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["phase1_export_run.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_phase1_export_keyword_hit_run_id",
        "phase1_export_keyword_hit",
        ["run_id"],
        unique=False,
    )

    op.create_table(
        "phase1_export_crossgen_hit",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("signal", sa.String(256), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["phase1_export_run.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_phase1_export_crossgen_hit_run_id",
        "phase1_export_crossgen_hit",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_phase1_export_crossgen_hit_run_id", table_name="phase1_export_crossgen_hit")
    op.drop_table("phase1_export_crossgen_hit")
    op.drop_index("ix_phase1_export_keyword_hit_run_id", table_name="phase1_export_keyword_hit")
    op.drop_table("phase1_export_keyword_hit")
    op.drop_index("ix_phase1_export_category_run_id", table_name="phase1_export_category")
    op.drop_table("phase1_export_category")
    op.drop_index("ix_phase1_export_thread_thread_id", table_name="phase1_export_thread")
    op.drop_index("ix_phase1_export_thread_run_id", table_name="phase1_export_thread")
    op.drop_table("phase1_export_thread")
    op.drop_index("ix_phase1_export_run_exported_at", table_name="phase1_export_run")
    op.drop_table("phase1_export_run")
