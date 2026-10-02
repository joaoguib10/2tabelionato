"""auditoria minima das execucoes de IA em consultas

Revision ID: 7f3c1a9b6d20
Revises: e91a4f3d2c10
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7f3c1a9b6d20"
down_revision: Union[str, Sequence[str], None] = "e91a4f3d2c10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "consultas_historico",
        sa.Column(
            "tipo_tarefa",
            sa.String(30),
            nullable=False,
            server_default="CONSULTA",
        ),
    )
    op.add_column(
        "consultas_historico",
        sa.Column("prompt_version", sa.String(30), nullable=True),
    )
    op.add_column(
        "consultas_historico",
        sa.Column("modelo_ia", sa.String(150), nullable=True),
    )
    op.add_column(
        "consultas_historico",
        sa.Column("modelo_versao", sa.String(100), nullable=True),
    )
    op.add_column(
        "consultas_historico",
        sa.Column("parametros_ia", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("consultas_historico", "parametros_ia")
    op.drop_column("consultas_historico", "modelo_versao")
    op.drop_column("consultas_historico", "modelo_ia")
    op.drop_column("consultas_historico", "prompt_version")
    op.drop_column("consultas_historico", "tipo_tarefa")
