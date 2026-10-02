"""Diagnóstico técnico de extração, independente da governança."""

import sqlalchemy as sa
from alembic import op

revision = "b92e4c71a630"
down_revision = "7f3c1a9b6d20"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "documentos",
        sa.Column(
            "situacao_extracao",
            sa.String(30),
            nullable=False,
            server_default="PENDENTE_VERIFICACAO",
        ),
    )
    op.add_column(
        "documentos", sa.Column("diagnostico_extracao", sa.JSON(), nullable=True)
    )
    op.add_column(
        "documento_paginas",
        sa.Column(
            "metodo_extracao",
            sa.String(20),
            nullable=False,
            server_default="NAO_VERIFICADO",
        ),
    )
    op.add_column(
        "documento_paginas",
        sa.Column(
            "situacao_extracao",
            sa.String(30),
            nullable=False,
            server_default="NAO_VERIFICADA",
        ),
    )


def downgrade():
    op.drop_column("documento_paginas", "situacao_extracao")
    op.drop_column("documento_paginas", "metodo_extracao")
    op.drop_column("documentos", "diagnostico_extracao")
    op.drop_column("documentos", "situacao_extracao")
