"""Add thread link column

Revision ID: 002
Revises: 001
Create Date: 2025-02-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "threads",
        sa.Column("link", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("threads", "link")
