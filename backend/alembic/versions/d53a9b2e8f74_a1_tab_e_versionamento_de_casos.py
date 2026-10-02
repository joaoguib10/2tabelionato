"""A1, TAB e versionamento de casos.

Revision ID: d53a9b2e8f74
Revises: c42f8a1d7e63
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d53a9b2e8f74"
down_revision: Union[str, Sequence[str], None] = "c42f8a1d7e63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "caso_versoes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("caso_id", sa.Uuid(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("hash_estado", sa.String(length=64), nullable=False),
        sa.Column("motivo", sa.String(length=200), nullable=False),
        sa.Column("fatos_snapshot", sa.JSON(), nullable=False),
        sa.Column("documentos_snapshot", sa.JSON(), nullable=False),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["caso_id"], ["casos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["criado_por"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("caso_id", "numero", name="uq_caso_versoes_numero"),
        sa.UniqueConstraint("caso_id", "hash_estado", name="uq_caso_versoes_hash"),
    )
    op.create_index(
        "ix_caso_versoes_caso_created_at",
        "caso_versoes",
        ["caso_id", "created_at"],
    )

    op.create_table(
        "caso_analises",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("caso_id", sa.Uuid(), nullable=False),
        sa.Column("versao_id", sa.Uuid(), nullable=False),
        sa.Column("status_evidencia", sa.String(length=30), nullable=False),
        sa.Column("resumo", sa.Text(), nullable=False),
        sa.Column("requisitos", sa.JSON(), nullable=False),
        sa.Column("impedimentos", sa.JSON(), nullable=False),
        sa.Column("pendencias", sa.JSON(), nullable=False),
        sa.Column("fontes_snapshot", sa.JSON(), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("modelo_ia", sa.String(length=150), nullable=True),
        sa.Column("gerado_por", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["caso_id"], ["casos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["versao_id"], ["caso_versoes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["gerado_por"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_caso_analises_caso_created_at",
        "caso_analises",
        ["caso_id", "created_at"],
    )

    op.create_table(
        "caso_decisoes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("caso_id", sa.Uuid(), nullable=False),
        sa.Column("analise_id", sa.Uuid(), nullable=False),
        sa.Column("decisao", sa.String(length=20), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("fundamentacao", sa.Text(), nullable=True),
        sa.Column("escopo", sa.String(length=500), nullable=True),
        sa.Column("decidido_por", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "decisao IN ('APROVAR', 'EXIGENCIA', 'RECUSAR', 'OUTRA')",
            name="ck_caso_decisoes_decisao",
        ),
        sa.ForeignKeyConstraint(["caso_id"], ["casos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["analise_id"], ["caso_analises.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["decidido_por"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_caso_decisoes_caso_created_at",
        "caso_decisoes",
        ["caso_id", "created_at"],
    )

    op.create_table(
        "ata_trabalhos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("nome_arquivo", sa.String(length=255), nullable=False),
        sa.Column("hash_arquivo", sa.String(length=64), nullable=False),
        sa.Column("caminho_temporario", sa.String(length=500), nullable=False),
        sa.Column("resultado", sa.Text(), nullable=True),
        sa.Column("diagnostico", sa.JSON(), nullable=True),
        sa.Column("erro_processamento", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("concluido_em", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('PROCESSANDO', 'PRONTO', 'PRONTO_PARCIAL', 'ERRO')",
            name="ck_ata_trabalhos_status",
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ata_trabalhos_usuario_created_at",
        "ata_trabalhos",
        ["usuario_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ata_trabalhos_usuario_created_at", table_name="ata_trabalhos")
    op.drop_table("ata_trabalhos")
    op.drop_index("ix_caso_decisoes_caso_created_at", table_name="caso_decisoes")
    op.drop_table("caso_decisoes")
    op.drop_index("ix_caso_analises_caso_created_at", table_name="caso_analises")
    op.drop_table("caso_analises")
    op.drop_index("ix_caso_versoes_caso_created_at", table_name="caso_versoes")
    op.drop_table("caso_versoes")
