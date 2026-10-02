"""Chat temporario e fila persistente da Analise.

Revision ID: b12f3c4d5e6f
Revises: e64b1c3f9a20
"""

import sqlalchemy as sa
from alembic import op

revision = "b12f3c4d5e6f"
down_revision = "e64b1c3f9a20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "caso_mensagens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("caso_id", sa.Uuid(), nullable=False),
        sa.Column("papel", sa.String(length=20), nullable=False),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("analise_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "papel IN ('USUARIO', 'ASSISTENTE', 'SISTEMA')",
            name="ck_caso_mensagens_papel",
        ),
        sa.ForeignKeyConstraint(["caso_id"], ["casos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["analise_id"], ["caso_analises.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_caso_mensagens_caso_created_at",
        "caso_mensagens",
        ["caso_id", "created_at"],
    )

    op.create_table(
        "caso_tarefas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("caso_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.String(length=60), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="PENDENTE"
        ),
        sa.Column("caso_documento_id", sa.Uuid(), nullable=True),
        sa.Column("tentativa", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("iniciado_em", sa.DateTime(), nullable=True),
        sa.Column("concluido_em", sa.DateTime(), nullable=True),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDENTE', 'PROCESSANDO', 'CONCLUIDA', 'ERRO', 'CANCELADA')",
            name="ck_caso_tarefas_status",
        ),
        sa.ForeignKeyConstraint(["caso_id"], ["casos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["caso_documento_id"], ["caso_documentos.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["criado_por"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_caso_tarefas_caso_created_at",
        "caso_tarefas",
        ["caso_id", "created_at"],
    )
    op.create_index(
        "ix_caso_tarefas_status_created_at",
        "caso_tarefas",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_caso_tarefas_status_created_at", table_name="caso_tarefas")
    op.drop_index("ix_caso_tarefas_caso_created_at", table_name="caso_tarefas")
    op.drop_table("caso_tarefas")
    op.drop_index("ix_caso_mensagens_caso_created_at", table_name="caso_mensagens")
    op.drop_table("caso_mensagens")
