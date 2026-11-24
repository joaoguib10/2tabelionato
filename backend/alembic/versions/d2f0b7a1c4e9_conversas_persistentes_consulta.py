"""Agrupa perguntas e respostas em conversas retomáveis da Consulta.

Revision ID: d2f0b7a1c4e9
Revises: b12f3c4d5e6f, c38e920f4a61
"""

import re
import uuid

import sqlalchemy as sa
from alembic import op

revision = "d2f0b7a1c4e9"
down_revision = ("b12f3c4d5e6f", "c38e920f4a61")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultas_conversas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("titulo", sa.String(length=150), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_consultas_conversas_usuario_updated_at",
        "consultas_conversas",
        ["usuario_id", "updated_at"],
    )
    op.add_column(
        "consultas_historico",
        sa.Column("conversa_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_consultas_historico_conversa_id",
        "consultas_historico",
        "consultas_conversas",
        ["conversa_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_consultas_historico_conversa_id",
        "consultas_historico",
        ["conversa_id"],
    )

    # O histórico anterior guardava cada pergunta sem vínculo de conversa.
    # Preservamos cada registro como uma conversa individual, sem inventar
    # encadeamentos que não foram persistidos no banco.
    conexao = op.get_bind()
    historico = sa.table(
        "consultas_historico",
        sa.column("id", sa.Uuid()),
        sa.column("usuario_id", sa.Uuid()),
        sa.column("pergunta", sa.Text()),
        sa.column("created_at", sa.DateTime()),
        sa.column("conversa_id", sa.Uuid()),
    )
    conversas = sa.table(
        "consultas_conversas",
        sa.column("id", sa.Uuid()),
        sa.column("usuario_id", sa.Uuid()),
        sa.column("titulo", sa.String(length=150)),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    registros = conexao.execute(
        sa.select(
            historico.c.id,
            historico.c.usuario_id,
            historico.c.pergunta,
            historico.c.created_at,
        ).order_by(historico.c.created_at, historico.c.id)
    ).mappings().all()
    for registro in registros:
        pergunta = re.sub(r"\s+", " ", registro["pergunta"]).strip()
        titulo = pergunta if len(pergunta) <= 150 else f"{pergunta[:147].rstrip()}..."
        conversa_id = uuid.uuid4()
        conexao.execute(
            conversas.insert().values(
                id=conversa_id,
                usuario_id=registro["usuario_id"],
                titulo=titulo,
                created_at=registro["created_at"],
                updated_at=registro["created_at"],
            )
        )
        conexao.execute(
            historico.update()
            .where(historico.c.id == registro["id"])
            .values(conversa_id=conversa_id)
        )


def downgrade() -> None:
    op.drop_index(
        "ix_consultas_historico_conversa_id",
        table_name="consultas_historico",
    )
    op.drop_constraint(
        "fk_consultas_historico_conversa_id",
        "consultas_historico",
        type_="foreignkey",
    )
    op.drop_column("consultas_historico", "conversa_id")
    op.drop_index(
        "ix_consultas_conversas_usuario_updated_at",
        table_name="consultas_conversas",
    )
    op.drop_table("consultas_conversas")
