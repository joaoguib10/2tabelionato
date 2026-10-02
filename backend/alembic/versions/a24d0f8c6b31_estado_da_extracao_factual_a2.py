"""estado da extracao factual a2

Revision ID: a24d0f8c6b31
Revises: 8d06fc8d27e7
Create Date: 2026-09-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a24d0f8c6b31"
down_revision: Union[str, Sequence[str], None] = "8d06fc8d27e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "caso_documentos",
        sa.Column(
            "status_extracao_fatos",
            sa.String(length=30),
            server_default="NAO_INICIADO",
            nullable=False,
        ),
    )
    op.add_column(
        "caso_documentos",
        sa.Column("erro_extracao_fatos", sa.Text(), nullable=True),
    )
    op.add_column(
        "caso_documentos",
        sa.Column("diagnostico_extracao_fatos", sa.JSON(), nullable=True),
    )
    op.add_column(
        "caso_documentos",
        sa.Column("fatos_extraidos_em", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "caso_documentos",
        sa.Column("versao_extrator_fatos", sa.String(length=50), nullable=True),
    )
    op.alter_column("caso_documentos", "status_extracao_fatos", server_default=None)


def downgrade() -> None:
    op.drop_column("caso_documentos", "versao_extrator_fatos")
    op.drop_column("caso_documentos", "fatos_extraidos_em")
    op.drop_column("caso_documentos", "diagnostico_extracao_fatos")
    op.drop_column("caso_documentos", "erro_extracao_fatos")
    op.drop_column("caso_documentos", "status_extracao_fatos")
