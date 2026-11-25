"""Permite arquivar conversas da Consulta sem apagar o histórico.

Revision ID: c6f28a31d904
Revises: 7a4c8f2e1d93
"""

from alembic import op
import sqlalchemy as sa


revision = "c6f28a31d904"
down_revision = "7a4c8f2e1d93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "consultas_conversas",
        sa.Column("arquivada_em", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_consultas_conversas_usuario_arquivada_updated_at",
        "consultas_conversas",
        ["usuario_id", "arquivada_em", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_consultas_conversas_usuario_arquivada_updated_at",
        table_name="consultas_conversas",
    )
    op.drop_column("consultas_conversas", "arquivada_em")
