"""Transforma trabalhos temporários de Ata em processos com etapa de upload.

Revision ID: c9e2f71a4b63
Revises: b12f3c4d5e6f
Create Date: 2026-10-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9e2f71a4b63"
down_revision: Union[str, Sequence[str], None] = "b12f3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ata_trabalhos") as batch:
        batch.add_column(sa.Column("titulo", sa.String(length=200), nullable=True))
        batch.drop_constraint("ck_ata_trabalhos_status", type_="check")
        batch.create_check_constraint(
            "ck_ata_trabalhos_status",
            "status IN ('ABERTO', 'PROCESSANDO', 'PRONTO', 'PRONTO_PARCIAL', 'ERRO')",
        )
        batch.alter_column(
            "nome_arquivo",
            existing_type=sa.String(length=255),
            nullable=True,
        )
        batch.alter_column(
            "hash_arquivo",
            existing_type=sa.String(length=64),
            nullable=True,
        )
        batch.alter_column(
            "caminho_temporario",
            existing_type=sa.String(length=500),
            nullable=True,
        )

    op.execute(
        "UPDATE ata_trabalhos "
        "SET titulo = substr(COALESCE(NULLIF(nome_arquivo, ''), 'Ata Notarial'), 1, 200) "
        "WHERE titulo IS NULL"
    )

    with op.batch_alter_table("ata_trabalhos") as batch:
        batch.alter_column(
            "titulo",
            existing_type=sa.String(length=200),
            nullable=False,
        )


def downgrade() -> None:
    op.execute(
        "UPDATE ata_trabalhos SET status = 'ERRO', "
        "nome_arquivo = COALESCE(nome_arquivo, titulo), "
        "hash_arquivo = COALESCE(hash_arquivo, 'sem-arquivo'), "
        "caminho_temporario = COALESCE(caminho_temporario, '') "
        "WHERE status = 'ABERTO'"
    )
    with op.batch_alter_table("ata_trabalhos") as batch:
        batch.drop_constraint("ck_ata_trabalhos_status", type_="check")
        batch.create_check_constraint(
            "ck_ata_trabalhos_status",
            "status IN ('PROCESSANDO', 'PRONTO', 'PRONTO_PARCIAL', 'ERRO')",
        )
        batch.alter_column(
            "nome_arquivo",
            existing_type=sa.String(length=255),
            nullable=False,
        )
        batch.alter_column(
            "hash_arquivo",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        batch.alter_column(
            "caminho_temporario",
            existing_type=sa.String(length=500),
            nullable=False,
        )
        batch.drop_column("titulo")
