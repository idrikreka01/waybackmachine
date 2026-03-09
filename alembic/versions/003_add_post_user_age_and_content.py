"""Add user_age and post_content to posts

Revision ID: 003
Revises: 002
Create Date: 2025-02-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("user_age", sa.Integer(), nullable=True))
    op.add_column("posts", sa.Column("post_content", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("posts", "post_content")
    op.drop_column("posts", "user_age")
