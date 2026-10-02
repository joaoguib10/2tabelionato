"""adiciona embeddings aos chunks

Revision ID: b55821e1cf5d
Revises: d8111a7e8e73
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "b55821e1cf5d"
down_revision: Union[str, Sequence[str], None] = "d8111a7e8e73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "documento_chunks",
        sa.Column(
            "embedding",
            Vector(768),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "documento_chunks",
        "embedding",
    )
