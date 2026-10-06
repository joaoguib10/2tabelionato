"""Indexa o texto dos entendimentos para recuperação por palavras-chave.

Revision ID: e2c4f97a18b3
Revises: d1a6c83f9b24
Create Date: 2026-10-06
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e2c4f97a18b3"
down_revision: Union[str, Sequence[str], None] = "d1a6c83f9b24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_documentos_busca_textual
        ON documentos USING gin (
            to_tsvector(
                'portuguese',
                coalesce(titulo, '') || ' ' || coalesce(descricao, '')
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_documentos_busca_textual")
