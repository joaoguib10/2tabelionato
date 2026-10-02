"""seguranca e deduplicacao documental

Revision ID: c7d3e8a4b912
Revises: f4c91a72d6e0
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7d3e8a4b912"
down_revision: Union[str, Sequence[str], None] = "f4c91a72d6e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documentos", sa.Column("hash_arquivo", sa.String(64), nullable=True))
    op.add_column(
        "documentos",
        sa.Column(
            "status_seguranca",
            sa.String(20),
            nullable=False,
            server_default="PENDENTE",
        ),
    )
    op.add_column("documentos", sa.Column("alerta_seguranca", sa.Text(), nullable=True))
    op.create_unique_constraint(
        "uq_documentos_hash_arquivo",
        "documentos",
        ["hash_arquivo"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_documentos_hash_arquivo", "documentos", type_="unique")
    op.drop_column("documentos", "alerta_seguranca")
    op.drop_column("documentos", "status_seguranca")
    op.drop_column("documentos", "hash_arquivo")
