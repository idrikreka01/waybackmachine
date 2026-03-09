"""Initial schema: categories, subcategories, threads, posts

Revision ID: 001
Revises:
Create Date: 2025-02-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("link", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "subcategories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("link", sa.Text(), nullable=False),
        sa.Column("threads_no", sa.Integer(), nullable=False),
        sa.Column("posts_no", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "threads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("replies_no", sa.Integer(), nullable=False),
        sa.Column("views_no", sa.Integer(), nullable=False),
        sa.Column("pagination", sa.Boolean(), nullable=False),
        sa.Column("is_sticky", sa.Boolean(), nullable=False),
        sa.Column("pagination_no", sa.Integer(), nullable=True),
        sa.Column("subcategory_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["subcategory_id"], ["subcategories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_joindate", sa.String(255), nullable=True),
        sa.Column("user_location", sa.String(512), nullable=True),
        sa.Column("user_posts", sa.Integer(), nullable=True),
        sa.Column("user_username", sa.String(255), nullable=True),
        sa.Column("user_register", sa.Boolean(), nullable=False),
        sa.Column("post_date_time", sa.DateTime(), nullable=True),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("post_page_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("posts")
    op.drop_table("threads")
    op.drop_table("subcategories")
    op.drop_table("categories")
