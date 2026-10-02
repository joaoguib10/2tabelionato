"""paginas e seguranca dos documentos de caso

Revision ID: 2c6b722fb2df
Revises: e7c5ec4d3cdf
Create Date: 2026-09-07 13:13:41.839353

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.

revision: str = "2c6b722fb2df"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = "e7c5ec4d3cdf"

branch_labels: Union[
    str,
    Sequence[str],
    None,
] = None

depends_on: Union[
    str,
    Sequence[str],
    None,
] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "caso_documento_paginas",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "caso_documento_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "pagina",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "pagina_confiavel",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "localizacao",
            sa.String(length=200),
            nullable=True,
        ),
        sa.Column(
            "conteudo",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "metodo_extracao",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "situacao_extracao",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["caso_documento_id"],
            ["caso_documentos.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "caso_documento_id",
            "pagina",
            name="uq_caso_documento_pagina",
        ),
    )

    op.create_index(
        "ix_caso_documento_paginas_documento",
        "caso_documento_paginas",
        ["caso_documento_id"],
        unique=False,
    )

    op.add_column(
        "caso_documentos",
        sa.Column(
            "status_seguranca",
            sa.String(length=20),
            nullable=False,
            server_default="PENDENTE",
        ),
    )

    op.alter_column(
        "caso_documentos",
        "status_seguranca",
        server_default=None,
    )

    op.add_column(
        "caso_documentos",
        sa.Column(
            "alerta_seguranca",
            sa.Text(),
            nullable=True,
        ),
    )

    op.add_column(
        "caso_documentos",
        sa.Column(
            "processado_em",
            sa.DateTime(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column(
        "caso_documentos",
        "processado_em",
    )

    op.drop_column(
        "caso_documentos",
        "alerta_seguranca",
    )

    op.drop_column(
        "caso_documentos",
        "status_seguranca",
    )

    op.drop_index(
        "ix_caso_documento_paginas_documento",
        table_name=("caso_documento_paginas"),
    )

    op.drop_table("caso_documento_paginas")
