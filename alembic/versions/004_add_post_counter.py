"""Add post_counter to posts (display string e.g. #1, #3)

Revision ID: 004
Revises: 003
Create Date: 2025-02-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("post_counter", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("posts", "post_counter")
