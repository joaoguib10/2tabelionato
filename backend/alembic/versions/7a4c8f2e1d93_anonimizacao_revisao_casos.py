"""adiciona preparação local e revisão das versões anonimizadas dos casos

Revision ID: 7a4c8f2e1d93
Revises: f30c2a6e9b41
Create Date: 2026-11-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7a4c8f2e1d93"
down_revision: Union[str, Sequence[str], None] = "f30c2a6e9b41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "caso_documentos",
        sa.Column(
            "status_anonimizacao",
            sa.String(length=30),
            server_default="AGUARDANDO_EXTRACAO",
            nullable=False,
        ),
    )
    op.add_column(
        "caso_documentos", sa.Column("erro_anonimizacao", sa.Text(), nullable=True)
    )
    op.add_column(
        "caso_documentos",
        sa.Column("anonimizado_por", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_caso_documentos_anonimizado_por",
        "caso_documentos",
        "usuarios",
        ["anonimizado_por"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "caso_documentos",
        sa.Column("anonimizado_em", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "caso_documento_paginas",
        sa.Column("conteudo_anonimizado", sa.Text(), nullable=True),
    )
    op.add_column(
        "caso_documento_paginas",
        sa.Column("hash_conteudo_anonimizado", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("caso_documento_paginas", "hash_conteudo_anonimizado")
    op.drop_column("caso_documento_paginas", "conteudo_anonimizado")
    op.drop_column("caso_documentos", "anonimizado_em")
    op.drop_constraint(
        "fk_caso_documentos_anonimizado_por", "caso_documentos", type_="foreignkey"
    )
    op.drop_column("caso_documentos", "anonimizado_por")
    op.drop_column("caso_documentos", "erro_anonimizacao")
    op.drop_column("caso_documentos", "status_anonimizacao")
