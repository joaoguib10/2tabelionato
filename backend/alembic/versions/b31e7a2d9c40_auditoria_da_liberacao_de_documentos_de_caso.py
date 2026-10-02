"""auditoria da liberacao de documentos de caso

Revision ID: b31e7a2d9c40
Revises: a24d0f8c6b31
Create Date: 2026-09-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b31e7a2d9c40"
down_revision: Union[str, Sequence[str], None] = "a24d0f8c6b31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "caso_documentos",
        sa.Column("seguranca_liberada_por", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "caso_documentos",
        sa.Column("seguranca_liberada_em", sa.DateTime(), nullable=True),
    )
    op.create_foreign_key(
        "fk_caso_documentos_seguranca_liberada_por_usuarios",
        "caso_documentos",
        "usuarios",
        ["seguranca_liberada_por"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_caso_documentos_seguranca_liberada_por_usuarios",
        "caso_documentos",
        type_="foreignkey",
    )
    op.drop_column("caso_documentos", "seguranca_liberada_em")
    op.drop_column("caso_documentos", "seguranca_liberada_por")
