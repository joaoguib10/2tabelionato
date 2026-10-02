import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    AUTH_COOKIE_MAX_AGE_SECONDS,
    AUTH_COOKIE_NAME,
    AUTH_COOKIE_SAMESITE,
    AUTH_COOKIE_SECURE,
    SECRET_KEY,
)
from app.dependencies import get_db
from app.models import Usuario

if not SECRET_KEY:
    raise RuntimeError("Defina TABELEAO_SECRET_KEY no ambiente.")


ALGORITHM = "HS256"


def create_access_token(data: dict, minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)

    to_encode.update({"exp": expire})

    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
    except JWTError:
        return None


oauth2_scheme = HTTPBearer(auto_error=False)


def set_access_cookie(response: Response, access_token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=access_token,
        max_age=AUTH_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite=AUTH_COOKIE_SAMESITE,
        path="/",
    )


def clear_access_cookie(response: Response) -> None:
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")


def get_current_user(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    token_recebido = (
        credentials.credentials
        if credentials is not None
        else request.cookies.get(AUTH_COOKIE_NAME)
    )
    if not token_recebido:
        raise HTTPException(status_code=401, detail="Autenticação necessária.")
    payload = decode_access_token(token_recebido)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        identificador = uuid.UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    usuario = db.query(Usuario).filter(Usuario.id == identificador).first()

    if usuario is None or not usuario.ativo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado ou inativo.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if (
        payload.get("purpose") != "access"
        or payload.get("ver") != usuario.sessao_versao
        or usuario.senha_pendente
        or not usuario.mfa_ativo
    ):
        raise HTTPException(
            status_code=401, detail="Conclua a autenticação em dois fatores."
        )

    # Cada chamada autenticada renova o prazo. Sem atividade, o token expira
    # no intervalo configurado e o usuário precisa autenticar-se novamente.
    token_renovado = create_access_token(
        {
            "sub": str(usuario.id),
            "role": usuario.role,
            "purpose": "access",
            "ver": usuario.sessao_versao,
        }
    )
    response.headers["X-Access-Token"] = token_renovado
    set_access_cookie(response, token_renovado)
    return usuario
