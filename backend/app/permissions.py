from fastapi import Depends, HTTPException, status

from app.auth import get_current_user
from app.models import Usuario


def require_roles(*roles: str):
    def role_checker(
        usuario: Usuario = Depends(get_current_user),
    ) -> Usuario:
        if usuario.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não possui permissão para realizar esta ação.",
            )

        return usuario

    return role_checker
