"""Permite busca textual com ou sem acentos usando índices GIN.

Revision ID: f17a69c0b482
Revises: e2c4f97a18b3
Create Date: 2026-10-06
"""

from typing import Sequence, Union

from alembic import op

revision: str = "f17a69c0b482"
down_revision: Union[str, Sequence[str], None] = "e2c4f97a18b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CARACTERES_COM_ACENTO = "áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ"
CARACTERES_SEM_ACENTO = "aaaaeeiooouucAAAAEEIOOOUUC"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_documentos_busca_textual_normalizada
        ON documentos USING gin (
            to_tsvector(
                'portuguese',
                translate(
                    coalesce(titulo, '') || ' ' || coalesce(descricao, ''),
                    '{CARACTERES_COM_ACENTO}',
                    '{CARACTERES_SEM_ACENTO}'
                )
            )
        )
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_documento_chunks_busca_textual_normalizada
        ON documento_chunks USING gin (
            to_tsvector(
                'portuguese',
                translate(
                    conteudo,
                    '{CARACTERES_COM_ACENTO}',
                    '{CARACTERES_SEM_ACENTO}'
                )
            )
        )
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_documentos_busca_textual")


def downgrade() -> None:
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
    op.execute(
        "DROP INDEX IF EXISTS ix_documento_chunks_busca_textual_normalizada"
    )
    op.execute("DROP INDEX IF EXISTS ix_documentos_busca_textual_normalizada")
