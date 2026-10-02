"""Dados estruturados da análise de compra e venda.

Revision ID: e64b1c3f9a20
Revises: d53a9b2e8f74
Create Date: 2026-09-08
"""

import sqlalchemy as sa
from alembic import op

revision = "e64b1c3f9a20"
down_revision = "d53a9b2e8f74"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("casos", sa.Column("dados_ato", sa.JSON(), nullable=True))
    op.add_column(
        "casos",
        sa.Column(
            "status_dados_ato",
            sa.String(length=30),
            nullable=False,
            server_default="NAO_INICIADO",
        ),
    )
    op.add_column("casos", sa.Column("erro_dados_ato", sa.Text(), nullable=True))
    op.add_column(
        "casos",
        sa.Column("dados_ato_atualizados_em", sa.DateTime(), nullable=True),
    )
    op.alter_column("casos", "status_dados_ato", server_default=None)


def downgrade() -> None:
    op.drop_column("casos", "dados_ato_atualizados_em")
    op.drop_column("casos", "erro_dados_ato")
    op.drop_column("casos", "status_dados_ato")
    op.drop_column("casos", "dados_ato")
