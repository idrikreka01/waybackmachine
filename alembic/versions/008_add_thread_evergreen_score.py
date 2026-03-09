"""Add thread_evergreen_score table for Phase 1 SEO triage.

Revision ID: 008
Revises: 007
Create Date: 2025-02-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "thread_evergreen_score",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("scoring_version", sa.String(32), nullable=False),
        sa.Column("final_score", sa.Integer(), nullable=False),
        sa.Column("raw_score", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id"),
    )
    op.create_index(
        "ix_thread_evergreen_score_decision",
        "thread_evergreen_score",
        ["decision"],
        unique=False,
    )
    op.create_index(
        "ix_thread_evergreen_score_final_score",
        "thread_evergreen_score",
        ["final_score"],
        unique=False,
    )
    op.create_index(
        "ix_thread_evergreen_score_thread_id",
        "thread_evergreen_score",
        ["thread_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_thread_evergreen_score_thread_id", table_name="thread_evergreen_score")
    op.drop_index("ix_thread_evergreen_score_final_score", table_name="thread_evergreen_score")
    op.drop_index("ix_thread_evergreen_score_decision", table_name="thread_evergreen_score")
    op.drop_table("thread_evergreen_score")
