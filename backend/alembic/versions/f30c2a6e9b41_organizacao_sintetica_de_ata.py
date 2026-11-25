"""Registra organização externa opcional e sintética da Ata.

Revision ID: f30c2a6e9b41
Revises: bb82f239a16c, d2f0b7a1c4e9
Create Date: 2026-11-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f30c2a6e9b41"
down_revision: Union[str, Sequence[str], None] = (
    "bb82f239a16c",
    "d2f0b7a1c4e9",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ata_trabalhos",
        sa.Column("resultado_organizado", sa.Text(), nullable=True),
    )
    op.add_column(
        "ata_trabalhos",
        sa.Column(
            "gemini_organizacao_status",
            sa.String(length=20),
            server_default="NAO_SOLICITADA",
            nullable=False,
        ),
    )
    op.add_column(
        "ata_trabalhos",
        sa.Column(
            "gemini_organizacao_sintetico_confirmado",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "ata_trabalhos",
        sa.Column("gemini_organizacao_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "ata_trabalhos",
        sa.Column(
            "gemini_organizacao_usuario_id",
            sa.Uuid(),
            nullable=True,
        ),
    )
    op.add_column(
        "ata_trabalhos",
        sa.Column("gemini_organizacao_em", sa.DateTime(), nullable=True),
    )
    op.create_foreign_key(
        "fk_ata_trabalhos_gemini_usuario",
        "ata_trabalhos",
        "usuarios",
        ["gemini_organizacao_usuario_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_ata_trabalhos_gemini_organizacao_status",
        "ata_trabalhos",
        "gemini_organizacao_status IN "
        "('NAO_SOLICITADA', 'PROCESSANDO', 'CONCLUIDA', 'ERRO')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_ata_trabalhos_gemini_organizacao_status",
        "ata_trabalhos",
        type_="check",
    )
    op.drop_constraint(
        "fk_ata_trabalhos_gemini_usuario",
        "ata_trabalhos",
        type_="foreignkey",
    )
    op.drop_column("ata_trabalhos", "gemini_organizacao_em")
    op.drop_column("ata_trabalhos", "gemini_organizacao_usuario_id")
    op.drop_column("ata_trabalhos", "gemini_organizacao_hash")
    op.drop_column("ata_trabalhos", "gemini_organizacao_sintetico_confirmado")
    op.drop_column("ata_trabalhos", "gemini_organizacao_status")
    op.drop_column("ata_trabalhos", "resultado_organizado")
