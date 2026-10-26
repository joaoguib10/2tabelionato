"""gateway externo com classificação, isolamento e fila durável

Revision ID: bb82f239a16c
Revises: f17a69c0b482
Create Date: 2026-10-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "bb82f239a16c"
down_revision: Union[str, Sequence[str], None] = "f17a69c0b482"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documentos",
        sa.Column(
            "liberacao_externa",
            sa.String(length=20),
            nullable=False,
            server_default="LOCAL_ONLY",
        ),
    )
    op.add_column(
        "casos",
        sa.Column(
            "classificacao_externa",
            sa.String(length=20),
            nullable=False,
            server_default="LOCAL_ONLY",
        ),
    )
    op.add_column(
        "casos",
        sa.Column("liberado_externamente_por", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "casos",
        sa.Column("liberado_externamente_em", sa.DateTime(), nullable=True),
    )
    op.create_foreign_key(
        "fk_casos_liberado_externamente_por_usuarios",
        "casos",
        "usuarios",
        ["liberado_externamente_por"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "ia_externa_configuracao",
        sa.Column("chave", sa.String(length=30), nullable=False),
        sa.Column(
            "consulta_habilitada",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "casos_sinteticos_habilitados",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("atualizado_por", sa.Uuid(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["atualizado_por"], ["usuarios.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("chave"),
    )
    op.create_table(
        "ia_externa_stores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("escopo", sa.String(length=20), nullable=False),
        sa.Column("caso_id", sa.String(length=36), nullable=True),
        sa.Column("nome_remoto", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=25), nullable=False),
        sa.Column("erro_codigo", sa.String(length=60), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "escopo IN ('INSTITUCIONAL', 'CASO')",
            name="ck_ia_externa_stores_escopo",
        ),
        sa.CheckConstraint(
            "status IN ('PENDENTE', 'ATIVO', 'EXCLUSAO_PENDENTE', 'ERRO')",
            name="ck_ia_externa_stores_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("escopo", "caso_id", name="uq_ia_externa_store_escopo_caso"),
    )
    op.create_index(
        "ix_ia_externa_stores_escopo_status",
        "ia_externa_stores",
        ["escopo", "status"],
    )
    op.create_table(
        "ia_externa_fontes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=True),
        sa.Column("escopo", sa.String(length=20), nullable=False),
        sa.Column("tipo_fonte", sa.String(length=20), nullable=False),
        sa.Column("fonte_local_id", sa.String(length=64), nullable=False),
        sa.Column("documento_id", sa.Uuid(), nullable=True),
        sa.Column("revisao_id", sa.Uuid(), nullable=True),
        sa.Column("caso_id", sa.String(length=36), nullable=True),
        sa.Column("caso_documento_id", sa.Uuid(), nullable=True),
        sa.Column("tier", sa.String(length=20), nullable=False),
        sa.Column("pagina", sa.Integer(), nullable=True),
        sa.Column("localizacao", sa.String(length=200), nullable=True),
        sa.Column("artigo", sa.String(length=50), nullable=True),
        sa.Column("versao_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "classificacao",
            sa.String(length=20),
            nullable=False,
            server_default="LOCAL_ONLY",
        ),
        sa.Column("nome_remoto", sa.String(length=255), nullable=False),
        sa.Column("documento_remoto", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=25), nullable=False),
        sa.Column("liberado_por", sa.Uuid(), nullable=True),
        sa.Column("liberado_em", sa.DateTime(), nullable=True),
        sa.Column("erro_codigo", sa.String(length=60), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "escopo IN ('INSTITUCIONAL', 'CASO')",
            name="ck_ia_externa_fontes_escopo",
        ),
        sa.CheckConstraint(
            "tipo_fonte IN ('DOCUMENTO', 'REVISAO', 'CASO_PAGINA')",
            name="ck_ia_externa_fontes_tipo",
        ),
        sa.CheckConstraint(
            "classificacao IN ('PUBLICO', 'SINTETICO', 'LOCAL_ONLY')",
            name="ck_ia_externa_fontes_classificacao",
        ),
        sa.CheckConstraint(
            "status IN ('PENDENTE', 'INDEXADO', 'EXCLUSAO_PENDENTE', 'LOCAL_ONLY', 'ERRO')",
            name="ck_ia_externa_fontes_status",
        ),
        sa.ForeignKeyConstraint(["store_id"], ["ia_externa_stores.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["documento_id"], ["documentos.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revisao_id"], ["consulta_revisoes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["caso_documento_id"], ["caso_documentos.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["liberado_por"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nome_remoto", name="uq_ia_externa_fontes_nome_remoto"),
    )
    op.create_index(
        "ix_ia_externa_fontes_escopo_tier_status",
        "ia_externa_fontes",
        ["escopo", "tier", "status"],
    )
    op.create_index(
        "ix_ia_externa_fontes_documento_pagina",
        "ia_externa_fontes",
        ["documento_id", "pagina"],
    )
    op.create_index(
        "ix_ia_externa_fontes_caso_pagina",
        "ia_externa_fontes",
        ["caso_id", "pagina"],
    )
    op.create_table(
        "ia_externa_fila",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("acao", sa.String(length=25), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("chave_idempotencia", sa.String(length=160), nullable=False),
        sa.Column("fonte_id", sa.Uuid(), nullable=True),
        sa.Column("store_id", sa.Uuid(), nullable=True),
        sa.Column("nome_store_remoto", sa.String(length=255), nullable=True),
        sa.Column("nome_fonte_remota", sa.String(length=255), nullable=True),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("erro_codigo", sa.String(length=60), nullable=True),
        sa.Column(
            "proxima_tentativa_em",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("iniciado_em", sa.DateTime(), nullable=True),
        sa.Column("concluido_em", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "acao IN ('SINCRONIZAR_FONTE', 'EXCLUIR_FONTE', 'EXCLUIR_STORE')",
            name="ck_ia_externa_fila_acao",
        ),
        sa.CheckConstraint(
            "status IN ('PENDENTE', 'PROCESSANDO', 'CONCLUIDA', 'ERRO')",
            name="ck_ia_externa_fila_status",
        ),
        sa.ForeignKeyConstraint(["fonte_id"], ["ia_externa_fontes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["store_id"], ["ia_externa_stores.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chave_idempotencia", name="uq_ia_externa_fila_idempotencia"),
    )
    op.create_index(
        "ix_ia_externa_fila_status_proxima",
        "ia_externa_fila",
        ["status", "proxima_tentativa_em"],
    )


def downgrade() -> None:
    op.drop_index("ix_ia_externa_fila_status_proxima", table_name="ia_externa_fila")
    op.drop_table("ia_externa_fila")
    op.drop_index("ix_ia_externa_fontes_caso_pagina", table_name="ia_externa_fontes")
    op.drop_index(
        "ix_ia_externa_fontes_documento_pagina", table_name="ia_externa_fontes"
    )
    op.drop_index(
        "ix_ia_externa_fontes_escopo_tier_status", table_name="ia_externa_fontes"
    )
    op.drop_table("ia_externa_fontes")
    op.drop_index("ix_ia_externa_stores_escopo_status", table_name="ia_externa_stores")
    op.drop_table("ia_externa_stores")
    op.drop_table("ia_externa_configuracao")
    op.drop_constraint(
        "fk_casos_liberado_externamente_por_usuarios", "casos", type_="foreignkey"
    )
    op.drop_column("casos", "liberado_externamente_em")
    op.drop_column("casos", "liberado_externamente_por")
    op.drop_column("casos", "classificacao_externa")
    op.drop_column("documentos", "liberacao_externa")
