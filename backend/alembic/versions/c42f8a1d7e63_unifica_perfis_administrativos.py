"""Unifica perfis administrativos.

Revision ID: c42f8a1d7e63
Revises: b31e7a2d9c40
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c42f8a1d7e63"
down_revision: Union[str, Sequence[str], None] = "b31e7a2d9c40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A ordem evita que o antigo ADMIN seja confundido com o novo ADMIN.
    op.execute(
        """
        UPDATE usuarios
        SET role = 'USUARIO', sessao_versao = sessao_versao + 1
        WHERE role = 'ADMIN'
        """
    )
    op.execute(
        """
        UPDATE usuarios
        SET role = 'ADMIN', sessao_versao = sessao_versao + 1
        WHERE role = 'MASTER'
        """
    )


def downgrade() -> None:
    # O perfil administrativo único volta a se chamar MASTER. Usuários comuns
    # permanecem USUARIO, pois não é possível distinguir antigos ADMIN deles.
    op.execute(
        """
        UPDATE usuarios
        SET role = 'MASTER', sessao_versao = sessao_versao + 1
        WHERE role = 'ADMIN'
        """
    )
