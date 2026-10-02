"""TOTP RFC 6238 local. Segredos criptografados; códigos de recuperação não reversíveis."""

import base64
import hashlib
import hmac
import secrets
import struct
import time

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.config import SECRET_KEY
from app.models import EventoSeguranca


def cipher():
    # Chave separada por domínio, derivada do segredo de implantação; nunca armazenada no DB.
    key = hmac.new(
        SECRET_KEY.encode(), b"tabeleao/mfa/encryption/v1", hashlib.sha256
    ).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def gerar_segredo():
    return base64.b32encode(secrets.token_bytes(20)).decode()


def abrir_segredo(value):
    try:
        return cipher().decrypt(value.encode()).decode()
    except (InvalidToken, AttributeError):
        raise HTTPException(
            503, "Autenticador indisponível. Solicite recuperação local ao responsável."
        ) from None


def codigo_totp(secret, step=None):
    step = int(time.time() // 30) if step is None else step
    digest = hmac.new(
        base64.b32decode(secret), struct.pack(">Q", step), hashlib.sha1
    ).digest()
    offset = digest[-1] & 15
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{number % 1000000:06d}"


def verificar_totp(secret, code, last_step):
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        return None
    now = int(time.time() // 30)
    for step in [now, now - 1, now + 1]:
        if step > last_step and hmac.compare_digest(codigo_totp(secret, step), code):
            return step
    return None


def hash_recuperacao(code):
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def novos_codigos():
    codes = [secrets.token_hex(10).upper() for _ in range(10)]
    return codes, [hash_recuperacao(code) for code in codes]


def auditar(db, usuario, acao, ator=None):
    db.add(
        EventoSeguranca(
            usuario_id=usuario.id, ator_id=ator.id if ator else None, acao=acao
        )
    )


def redefinir_acesso(db, usuario, password_hash, ator=None):
    usuario.password_hash = password_hash
    usuario.senha_pendente = True
    usuario.mfa_ativo = False
    usuario.mfa_segredo = None
    usuario.mfa_ultimo_passo = -1
    usuario.mfa_tentativas = 0
    usuario.recuperacao_hashes = []
    usuario.tentativas_login = 0
    usuario.bloqueado_em = None
    usuario.sessao_versao += 1
    auditar(
        db,
        usuario,
        "RECUPERACAO_SERVIDOR" if ator is None else "RECUPERACAO_ADMIN",
        ator,
    )
