"""Senha, segundo fator local e auditoria; contas antigas entram em cadastramento."""

import sqlalchemy as sa
from alembic import op

revision = "c38e920f4a61"
down_revision = "b92e4c71a630"
branch_labels = None
depends_on = None


def upgrade():
    for column in [
        sa.Column(
            "senha_pendente", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("mfa_ativo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mfa_segredo", sa.Text(), nullable=True),
        sa.Column(
            "mfa_ultimo_passo", sa.Integer(), nullable=False, server_default="-1"
        ),
        sa.Column("mfa_tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recuperacao_hashes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("sessao_versao", sa.Integer(), nullable=False, server_default="0"),
    ]:
        op.add_column("usuarios", column)
    op.create_table(
        "eventos_seguranca",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id", ondelete="SET NULL")
        ),
        sa.Column(
            "ator_id", sa.Uuid(), sa.ForeignKey("usuarios.id", ondelete="SET NULL")
        ),
        sa.Column("acao", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("eventos_seguranca")
    for name in [
        "sessao_versao",
        "recuperacao_hashes",
        "mfa_tentativas",
        "mfa_ultimo_passo",
        "mfa_segredo",
        "mfa_ativo",
        "senha_pendente",
    ]:
        op.drop_column("usuarios", name)
