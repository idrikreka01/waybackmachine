"""Add thread_list_fetched to subcategories, posts_fetched to threads.

Revision ID: 006
Revises: 005
Create Date: 2025-02-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subcategories",
        sa.Column("thread_list_fetched", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column(
        "threads",
        sa.Column("posts_fetched", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("threads", "posts_fetched")
    op.drop_column("subcategories", "thread_list_fetched")
