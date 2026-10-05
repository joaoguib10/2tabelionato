"""Mantém compatibilidade com versões anteriores da API de Ata.

Revision ID: d1a6c83f9b24
Revises: c9e2f71a4b63
Create Date: 2026-10-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d1a6c83f9b24"
down_revision: Union[str, Sequence[str], None] = "c9e2f71a4b63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "ata_trabalhos",
        "titulo",
        existing_type=sa.String(length=200),
        existing_nullable=False,
        server_default="Ata Notarial",
    )


def downgrade() -> None:
    op.alter_column(
        "ata_trabalhos",
        "titulo",
        existing_type=sa.String(length=200),
        existing_nullable=False,
        server_default=None,
    )
