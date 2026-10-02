import hmac
import uuid

from app.auth import (
    clear_access_cookie,
    create_access_token,
    decode_access_token,
    get_current_user,
    set_access_cookie,
)
from app.config import MAX_LOGIN_ATTEMPTS, MFA_ENABLED
from app.dependencies import get_db
from app.models import Usuario, utc_now
from app.security import hash_password, validar_senha, verify_password
from app.services.two_factor import (
    abrir_segredo,
    auditar,
    cipher,
    gerar_segredo,
    hash_recuperacao,
    novos_codigos,
    verificar_totp,
)
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/auth", tags=["Autenticação"])


class Challenge(BaseModel):
    challenge_token: str = Field(max_length=2048)


class PasswordChallenge(Challenge):
    password: str = Field(max_length=72)
    _validar = field_validator("password")(validar_senha)


class CodeChallenge(Challenge):
    code: str = Field(min_length=1, max_length=64)
    recovery: bool = False


def token(usuario, purpose):
    dados = {
        "sub": str(usuario.id),
        "role": usuario.role,
        "purpose": purpose,
        "ver": usuario.sessao_versao,
        "mfa_bypassed": purpose == "access" and not MFA_ENABLED,
    }
    return (
        create_access_token(dados)
        if purpose == "access"
        else create_access_token(dados, minutes=5)
    )


def proxima_etapa(usuario, response):
    if usuario.senha_pendente:
        action = "password"
    elif not MFA_ENABLED:
        access_token = token(usuario, "access")
        set_access_cookie(response, access_token)
        return {"access_token": access_token, "token_type": "bearer"}
    else:
        action = "verify" if usuario.mfa_ativo else "setup"
    return {"action": action, "challenge_token": token(usuario, action)}


def desafiante(dados, db, purpose):
    payload = decode_access_token(dados.challenge_token) or {}
    try:
        user_id = uuid.UUID(payload.get("sub", ""))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(401, "Autenticação expirada. Entre novamente.") from None
    usuario = db.query(Usuario).filter(Usuario.id == user_id).with_for_update().first()
    if (
        not usuario
        or not usuario.ativo
        or payload.get("purpose") != purpose
        or payload.get("ver") != usuario.sessao_versao
    ):
        raise HTTPException(401, "Autenticação expirada. Entre novamente.")
    if (
        usuario.tentativas_login >= MAX_LOGIN_ATTEMPTS
        or (MFA_ENABLED and usuario.mfa_tentativas >= MAX_LOGIN_ATTEMPTS)
    ):
        raise HTTPException(
            423, "Acesso bloqueado. Solicite recuperação ao responsável."
        )
    expected = (
        "password"
        if usuario.senha_pendente
        else "verify" if usuario.mfa_ativo else "setup"
    )
    if purpose != expected:
        raise HTTPException(401, "Etapa de autenticação inválida.")
    return usuario


def falha_codigo(db, usuario):
    usuario.mfa_tentativas += 1
    auditar(db, usuario, "SEGUNDO_FATOR_INVALIDO")
    db.commit()
    raise HTTPException(
        423 if usuario.mfa_tentativas >= MAX_LOGIN_ATTEMPTS else 401,
        "Código inválido ou já utilizado. Se bloqueado, solicite recuperação.",
    )


@router.post("/login")
def login(
    response: Response,
    login_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    usuario = (
        db.query(Usuario)
        .filter(Usuario.username == login_data.username.strip().lower())
        .with_for_update()
        .first()
    )
    if not usuario or not usuario.ativo:
        raise HTTPException(401, "Usuário ou senha inválidos.")
    if (
        usuario.tentativas_login >= MAX_LOGIN_ATTEMPTS
        or (MFA_ENABLED and usuario.mfa_tentativas >= MAX_LOGIN_ATTEMPTS)
    ):
        raise HTTPException(
            423, "Acesso bloqueado. Solicite recuperação ao responsável."
        )
    if not verify_password(login_data.password, usuario.password_hash):
        usuario.tentativas_login += 1
        if usuario.tentativas_login >= MAX_LOGIN_ATTEMPTS:
            usuario.bloqueado_em = utc_now()
        auditar(db, usuario, "SENHA_INVALIDA")
        db.commit()
        raise HTTPException(
            423 if usuario.tentativas_login >= MAX_LOGIN_ATTEMPTS else 401,
            "Usuário ou senha inválidos.",
        )
    usuario.tentativas_login = 0
    usuario.bloqueado_em = None
    db.commit()
    return proxima_etapa(usuario, response)


@router.post("/password")
def password(
    dados: PasswordChallenge, response: Response, db: Session = Depends(get_db)
):
    response.headers["Cache-Control"] = "no-store"
    usuario = desafiante(dados, db, "password")
    if verify_password(dados.password, usuario.password_hash):
        raise HTTPException(422, "Escolha uma senha diferente da inicial.")
    usuario.password_hash = hash_password(dados.password)
    usuario.senha_pendente = False
    usuario.sessao_versao += 1
    auditar(db, usuario, "SENHA_CADASTRADA", usuario)
    db.commit()
    return proxima_etapa(usuario, response)


@router.post("/mfa/setup")
def setup(dados: Challenge, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    if not MFA_ENABLED:
        raise HTTPException(403, "O segundo fator está desativado nesta instância.")
    usuario = desafiante(dados, db, "setup")
    if not usuario.mfa_segredo:
        usuario.mfa_segredo = cipher().encrypt(gerar_segredo().encode()).decode()
        db.commit()
    secret = abrir_segredo(usuario.mfa_segredo)
    return {
        "secret": secret,
        "issuer": "Tabeleão",
        "algorithm": "SHA1",
        "digits": 6,
        "period": 30,
    }


@router.post("/mfa/confirm")
def confirm(dados: CodeChallenge, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    if not MFA_ENABLED:
        raise HTTPException(403, "O segundo fator está desativado nesta instância.")
    usuario = desafiante(dados, db, "setup")
    if not usuario.mfa_segredo:
        raise HTTPException(409, "Inicie o cadastro do autenticador.")
    secret = abrir_segredo(usuario.mfa_segredo)
    step = verificar_totp(secret, dados.code.strip(), usuario.mfa_ultimo_passo)
    if step is None:
        falha_codigo(db, usuario)
    codes, hashes = novos_codigos()
    usuario.recuperacao_hashes = hashes
    usuario.mfa_ativo = True
    usuario.mfa_tentativas = 0
    usuario.mfa_ultimo_passo = step
    usuario.sessao_versao += 1
    auditar(db, usuario, "MFA_CADASTRADO", usuario)
    db.commit()
    access_token = token(usuario, "access")
    set_access_cookie(response, access_token)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "recovery_codes": codes,
    }


@router.post("/mfa/verify")
def verify(dados: CodeChallenge, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    if not MFA_ENABLED:
        raise HTTPException(403, "O segundo fator está desativado nesta instância.")
    usuario = desafiante(dados, db, "verify")
    if dados.recovery:
        candidate = hash_recuperacao(dados.code)
        if not any(
            hmac.compare_digest(candidate, saved)
            for saved in usuario.recuperacao_hashes
        ):
            falha_codigo(db, usuario)
        usuario.mfa_ativo = False
        usuario.mfa_segredo = None
        usuario.mfa_ultimo_passo = -1
        usuario.recuperacao_hashes = []
        action = "RECUPERACAO_CODIGO"
    else:
        secret = abrir_segredo(usuario.mfa_segredo)
        step = verificar_totp(secret, dados.code.strip(), usuario.mfa_ultimo_passo)
        if step is None:
            falha_codigo(db, usuario)
        usuario.mfa_ultimo_passo = step
        action = "LOGIN_MFA"
    usuario.mfa_tentativas = 0
    usuario.sessao_versao += 1
    auditar(db, usuario, action, usuario)
    db.commit()
    if dados.recovery:
        clear_access_cookie(response)
        return proxima_etapa(usuario, response)
    access_token = token(usuario, "access")
    set_access_cookie(response, access_token)
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout", status_code=204)
def logout(response: Response):
    clear_access_cookie(response)
    return None


@router.get("/me")
def get_me(usuario: Usuario = Depends(get_current_user)):
    return {
        "id": str(usuario.id),
        "nome": usuario.nome,
        "username": usuario.username,
        "role": usuario.role,
        "ativo": usuario.ativo,
    }
