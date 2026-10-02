"""fila de revisoes humanas das consultas

Revision ID: e91a4f3d2c10
Revises: c7d3e8a4b912
Create Date: 2026-09-04
"""

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e91a4f3d2c10"
down_revision: Union[str, Sequence[str], None] = "c7d3e8a4b912"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "consulta_revisoes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("consulta_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="PENDENTE",
        ),
        sa.Column("responsavel_id", sa.Uuid(), nullable=True),
        sa.Column("resposta_humana", sa.Text(), nullable=True),
        sa.Column("respondido_por", sa.Uuid(), nullable=True),
        sa.Column("respondida_em", sa.DateTime(), nullable=True),
        sa.Column("entendimento_documento_id", sa.Uuid(), nullable=True),
        sa.Column("encerrada_em", sa.DateTime(), nullable=True),
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
            "status IN ('PENDENTE', 'EM_ANALISE', 'RESPONDIDA', 'ENCERRADA')",
            name="ck_consulta_revisoes_status",
        ),
        sa.ForeignKeyConstraint(
            ["consulta_id"],
            ["consultas_historico.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["responsavel_id"],
            ["usuarios.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["respondido_por"],
            ["usuarios.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["entendimento_documento_id"],
            ["documentos.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "consulta_id",
            name="uq_consulta_revisoes_consulta_id",
        ),
        sa.UniqueConstraint(
            "entendimento_documento_id",
            name="uq_consulta_revisoes_entendimento_documento_id",
        ),
    )
    op.create_index(
        "ix_consulta_revisoes_status_created_at",
        "consulta_revisoes",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_consulta_revisoes_responsavel_id",
        "consulta_revisoes",
        ["responsavel_id"],
    )

    conexao = op.get_bind()
    consultas = sa.table(
        "consultas_historico",
        sa.column("id", sa.Uuid()),
        sa.column("produtiva", sa.Boolean()),
    )
    revisoes = sa.table(
        "consulta_revisoes",
        sa.column("id", sa.Uuid()),
        sa.column("consulta_id", sa.Uuid()),
        sa.column("status", sa.String()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    consultas_negativas = conexao.execute(
        sa.select(consultas.c.id).where(consultas.c.produtiva.is_(False))
    ).scalars()
    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    registros = [
        {
            "id": uuid.uuid4(),
            "consulta_id": consulta_id,
            "status": "PENDENTE",
            "created_at": agora,
            "updated_at": agora,
        }
        for consulta_id in consultas_negativas
    ]
    if registros:
        conexao.execute(sa.insert(revisoes), registros)


def downgrade() -> None:
    op.drop_index(
        "ix_consulta_revisoes_responsavel_id",
        table_name="consulta_revisoes",
    )
    op.drop_index(
        "ix_consulta_revisoes_status_created_at",
        table_name="consulta_revisoes",
    )
    op.drop_table("consulta_revisoes")
