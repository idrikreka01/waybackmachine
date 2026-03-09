"""Drop main_categories, main_category_rules, thread_sorted (no longer used).

Revision ID: 007
Revises: 006
Create Date: 2025-02-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        "ix_thread_sorted_main_category_id",
        table_name="thread_sorted",
        if_exists=True,
    )
    op.drop_index(
        "ix_main_category_rules_main_category_id",
        table_name="main_category_rules",
        if_exists=True,
    )
    op.drop_table("thread_sorted", if_exists=True)
    op.drop_table("main_category_rules", if_exists=True)
    op.drop_table("main_categories", if_exists=True)


def downgrade() -> None:
    op.create_table(
        "main_categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "main_category_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("main_category_id", sa.Integer(), nullable=False),
        sa.Column("subcategory_label", sa.String(512), nullable=False, server_default=""),
        sa.Column("keywords_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["main_category_id"], ["main_categories.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "thread_sorted",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("main_category_id", sa.Integer(), nullable=True),
        sa.Column("subcategory_label", sa.String(512), nullable=False, server_default=""),
        sa.Column("match_source", sa.String(32), nullable=False, server_default="keyword"),
        sa.Column("matched_keywords", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["main_category_id"], ["main_categories.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id"),
    )
    op.create_index(
        "ix_main_category_rules_main_category_id",
        "main_category_rules",
        ["main_category_id"],
        unique=False,
    )
    op.create_index(
        "ix_thread_sorted_main_category_id",
        "thread_sorted",
        ["main_category_id"],
        unique=False,
    )
