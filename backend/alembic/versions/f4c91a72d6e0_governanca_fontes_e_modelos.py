"""governanca documental, modelos e snapshots de fontes

Revision ID: f4c91a72d6e0
Revises: a36f0d58c2b1
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4c91a72d6e0"
down_revision: Union[str, Sequence[str], None] = "a36f0d58c2b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documentos", sa.Column("tipo_ato", sa.String(50), nullable=True))
    op.add_column(
        "documentos",
        sa.Column("situacao", sa.String(20), nullable=False, server_default="RASCUNHO"),
    )
    op.add_column(
        "documentos", sa.Column("orgao_origem", sa.String(200), nullable=True)
    )
    op.add_column("documentos", sa.Column("versao", sa.String(100), nullable=True))
    op.add_column("documentos", sa.Column("jurisdicao", sa.String(150), nullable=True))
    op.add_column("documentos", sa.Column("vigencia_inicio", sa.Date(), nullable=True))
    op.add_column("documentos", sa.Column("vigencia_fim", sa.Date(), nullable=True))
    op.add_column("documentos", sa.Column("observacoes", sa.Text(), nullable=True))
    op.add_column("documentos", sa.Column("aprovado_por", sa.Uuid(), nullable=True))
    op.add_column("documentos", sa.Column("aprovado_em", sa.DateTime(), nullable=True))
    op.create_foreign_key(
        "fk_documentos_aprovado_por_usuarios",
        "documentos",
        "usuarios",
        ["aprovado_por"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_documentos_governanca_ia",
        "documentos",
        ["tipo", "tipo_ato", "situacao", "status", "ativo"],
    )

    op.add_column(
        "documento_paginas",
        sa.Column(
            "pagina_confiavel", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.add_column(
        "documento_paginas",
        sa.Column("localizacao", sa.String(200), nullable=True),
    )

    op.add_column(
        "documento_chunks",
        sa.Column(
            "artigo_confirmado", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "documento_chunks", sa.Column("capitulo", sa.String(200), nullable=True)
    )
    op.add_column("documento_chunks", sa.Column("secao", sa.String(200), nullable=True))
    op.add_column(
        "documento_chunks", sa.Column("paragrafo", sa.String(100), nullable=True)
    )
    op.add_column("documento_chunks", sa.Column("inciso", sa.String(50), nullable=True))
    op.add_column(
        "documento_chunks",
        sa.Column(
            "pagina_confiavel", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.add_column(
        "documento_chunks", sa.Column("localizacao", sa.String(200), nullable=True)
    )

    op.add_column(
        "consultas_historico",
        sa.Column(
            "situacao_resposta",
            sa.String(30),
            nullable=False,
            server_default="BASE_INSUFICIENTE",
        ),
    )
    op.add_column(
        "consultas_historico",
        sa.Column("feedback_motivo", sa.String(50), nullable=True),
    )
    op.add_column(
        "consultas_historico",
        sa.Column("feedback_comentario", sa.String(500), nullable=True),
    )

    op.create_table(
        "consulta_fontes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("consulta_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=True),
        sa.Column("documento_id", sa.Uuid(), nullable=True),
        sa.Column("fonte_id", sa.String(50), nullable=False),
        sa.Column("titulo_documento", sa.String(200), nullable=False),
        sa.Column("versao_documento", sa.String(100), nullable=True),
        sa.Column("pagina", sa.Integer(), nullable=True),
        sa.Column("localizacao", sa.String(200), nullable=True),
        sa.Column("artigo", sa.String(50), nullable=True),
        sa.Column("trecho", sa.Text(), nullable=False),
        sa.Column("pontuacao", sa.Float(), nullable=False),
        sa.Column("citada", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("recuperada", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["consulta_id"], ["consultas_historico.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"], ["documento_chunks.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["documento_id"], ["documentos.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_consulta_fontes_consulta_id", "consulta_fontes", ["consulta_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_consulta_fontes_consulta_id", table_name="consulta_fontes")
    op.drop_table("consulta_fontes")
    op.drop_column("consultas_historico", "feedback_comentario")
    op.drop_column("consultas_historico", "feedback_motivo")
    op.drop_column("consultas_historico", "situacao_resposta")
    op.drop_column("documento_chunks", "localizacao")
    op.drop_column("documento_chunks", "pagina_confiavel")
    op.drop_column("documento_chunks", "inciso")
    op.drop_column("documento_chunks", "paragrafo")
    op.drop_column("documento_chunks", "secao")
    op.drop_column("documento_chunks", "capitulo")
    op.drop_column("documento_chunks", "artigo_confirmado")
    op.drop_column("documento_paginas", "localizacao")
    op.drop_column("documento_paginas", "pagina_confiavel")
    op.drop_index("ix_documentos_governanca_ia", table_name="documentos")
    op.drop_constraint(
        "fk_documentos_aprovado_por_usuarios", "documentos", type_="foreignkey"
    )
    op.drop_column("documentos", "aprovado_em")
    op.drop_column("documentos", "aprovado_por")
    op.drop_column("documentos", "observacoes")
    op.drop_column("documentos", "vigencia_fim")
    op.drop_column("documentos", "vigencia_inicio")
    op.drop_column("documentos", "jurisdicao")
    op.drop_column("documentos", "versao")
    op.drop_column("documentos", "orgao_origem")
    op.drop_column("documentos", "situacao")
    op.drop_column("documentos", "tipo_ato")
