"""ingestao, limite de login, historico e indices hibridos

Revision ID: a36f0d58c2b1
Revises: 8d95f6987e80
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a36f0d58c2b1"
down_revision: Union[str, Sequence[str], None] = "8d95f6987e80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "usuarios",
        sa.Column(
            "tentativas_login",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "usuarios",
        sa.Column("bloqueado_em", sa.DateTime(), nullable=True),
    )

    op.add_column(
        "documentos",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="PROCESSANDO",
        ),
    )
    op.add_column(
        "documentos",
        sa.Column("erro_processamento", sa.Text(), nullable=True),
    )
    op.add_column(
        "documentos",
        sa.Column(
            "total_paginas",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "documentos",
        sa.Column(
            "total_chunks",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "documentos",
        sa.Column("processado_em", sa.DateTime(), nullable=True),
    )

    op.execute(
        """
        UPDATE documentos AS d
        SET total_paginas = (
                SELECT count(*) FROM documento_paginas p
                WHERE p.documento_id = d.id
            ),
            total_chunks = (
                SELECT count(*) FROM documento_chunks c
                WHERE c.documento_id = d.id
            ),
            status = CASE WHEN EXISTS (
                SELECT 1 FROM documento_chunks c
                WHERE c.documento_id = d.id AND c.embedding IS NOT NULL
            ) THEN 'PRONTO' ELSE 'ERRO' END,
            erro_processamento = CASE WHEN EXISTS (
                SELECT 1 FROM documento_chunks c
                WHERE c.documento_id = d.id AND c.embedding IS NOT NULL
            ) THEN NULL ELSE 'Reprocesse o documento para concluir a indexação.' END,
            processado_em = CURRENT_TIMESTAMP
        """
    )

    op.create_table(
        "consultas_historico",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("pergunta", sa.Text(), nullable=False),
        sa.Column("resposta", sa.Text(), nullable=False),
        sa.Column(
            "confianca",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "confiavel",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "fonte_ids",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("produtiva", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_documento_chunks_busca_textual
        ON documento_chunks
        USING gin (to_tsvector('portuguese', conteudo))
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_documento_chunks_embedding_hnsw
        ON documento_chunks
        USING hnsw (embedding vector_cosine_ops)
        WHERE embedding IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_documento_chunks_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_documento_chunks_busca_textual")
    op.drop_table("consultas_historico")
    op.drop_column("documentos", "processado_em")
    op.drop_column("documentos", "total_chunks")
    op.drop_column("documentos", "total_paginas")
    op.drop_column("documentos", "erro_processamento")
    op.drop_column("documentos", "status")
    op.drop_column("usuarios", "bloqueado_em")
    op.drop_column("usuarios", "tentativas_login")
