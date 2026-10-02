import base64
import uuid

import pytest
from app.auth import create_access_token, decode_access_token
from app.models import EventoSeguranca
from app.security import hash_password
from app.services.two_factor import (
    cipher,
    codigo_totp,
    redefinir_acesso,
    verificar_totp,
)


@pytest.fixture(autouse=True)
def clock_estavel(monkeypatch):
    from types import SimpleNamespace

    from app.services import two_factor

    monkeypatch.setattr(two_factor, "time", SimpleNamespace(time=lambda: 1800000000))


def legacy(db, factory):
    u = factory("mfa-exemplo")
    u.senha_pendente = True
    u.mfa_ativo = False
    db.commit()
    return u


def enroll(client, db, factory):
    u = legacy(db, factory)
    reply = client.post(
        "/api/auth/login", data={"username": u.username, "password": "1234"}
    ).json()
    assert reply["action"] == "password"
    assert (
        client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer " + reply["challenge_token"]},
        ).status_code
        == 401
    )
    reply = client.post(
        "/api/auth/password",
        json={
            "challenge_token": reply["challenge_token"],
            "password": "Minha-frase-teste-2026",
        },
    ).json()
    challenge = reply["challenge_token"]
    setup = client.post("/api/auth/mfa/setup", json={"challenge_token": challenge})
    assert setup.headers["cache-control"] == "no-store"
    secret = setup.json()["secret"]
    db.refresh(u)
    assert u.mfa_segredo != secret
    assert cipher().decrypt(u.mfa_segredo.encode()).decode() == secret
    result = client.post(
        "/api/auth/mfa/confirm",
        json={"challenge_token": challenge, "code": codigo_totp(secret)},
    )
    assert result.status_code == 200
    assert (
        client.post(
            "/api/auth/mfa/confirm",
            json={"challenge_token": challenge, "code": codigo_totp(secret)},
        ).status_code
        == 401
    )
    return u, secret, result.json()


def test_totp_rfc6238_e_replay():
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert codigo_totp(secret, 1) == "287082"  # RFC: 94287082 truncado a seis dígitos
    assert verificar_totp(secret, "abcdef", -1) is None


def test_mfa_desativado_temporariamente_sem_apagar_cadastro(
    client, db, usuario_factory, monkeypatch
):
    from app import auth as auth_module
    from app.routers import auth

    monkeypatch.setattr(auth, "MFA_ENABLED", False)
    monkeypatch.setattr(auth_module, "MFA_ENABLED", False)
    usuario = usuario_factory("mfa-temporariamente-off")
    usuario.mfa_ativo = True
    usuario.mfa_segredo = "segredo-cifrado-preservado"
    db.commit()

    resposta = client.post(
        "/api/auth/login",
        data={"username": usuario.username, "password": "1234"},
    )
    assert resposta.status_code == 200
    assert resposta.json()["access_token"]
    assert "action" not in resposta.json()
    assert client.get("/api/auth/me").status_code == 200
    db.refresh(usuario)
    assert usuario.mfa_ativo
    assert usuario.mfa_segredo == "segredo-cifrado-preservado"

    challenge = {"challenge_token": "desativado-para-testes"}
    assert client.post("/api/auth/mfa/setup", json=challenge).status_code == 403
    assert client.post(
        "/api/auth/mfa/verify", json={**challenge, "code": "123456"}
    ).status_code == 403

    monkeypatch.setattr(auth_module, "MFA_ENABLED", True)
    assert client.get("/api/auth/me").status_code == 401


def test_primer_login_sem_mfa_ainda_exige_cadastro_de_senha(
    client, db, usuario_factory, monkeypatch
):
    from app import auth as auth_module
    from app.routers import auth

    monkeypatch.setattr(auth, "MFA_ENABLED", False)
    monkeypatch.setattr(auth_module, "MFA_ENABLED", False)
    usuario = usuario_factory("senha-inicial-sem-mfa")
    usuario.senha_pendente = True
    db.commit()

    etapa_senha = client.post(
        "/api/auth/login",
        data={"username": usuario.username, "password": "1234"},
    ).json()
    assert etapa_senha["action"] == "password"

    resposta = client.post(
        "/api/auth/password",
        json={
            "challenge_token": etapa_senha["challenge_token"],
            "password": "Minha-senha-teste-2026",
        },
    )
    assert resposta.status_code == 200
    assert resposta.json()["access_token"]
    assert "action" not in resposta.json()
    assert client.get("/api/auth/me").status_code == 200


def test_transicao_codigo_recuperacao_e_revogacao(client, db, usuario_factory):
    u, secret, result = enroll(client, db, usuario_factory)
    access = {"Authorization": "Bearer " + result["access_token"]}
    assert client.get("/api/auth/me", headers=access).status_code == 200
    db.refresh(u)
    assert all(code not in u.recuperacao_hashes for code in result["recovery_codes"])
    challenge = client.post(
        "/api/auth/login",
        data={"username": u.username, "password": "Minha-frase-teste-2026"},
    ).json()["challenge_token"]
    # Mesmo código de tempo que concluiu o cadastro não pode ser usado novamente.
    assert (
        client.post(
            "/api/auth/mfa/verify",
            json={"challenge_token": challenge, "code": codigo_totp(secret)},
        ).status_code
        == 401
    )
    response = client.post(
        "/api/auth/mfa/verify",
        json={
            "challenge_token": challenge,
            "code": result["recovery_codes"][0],
            "recovery": True,
        },
    )
    assert response.status_code == 200 and response.json()["action"] == "setup"
    assert "access_token" not in response.json()
    assert client.get("/api/auth/me", headers=access).status_code == 401
    assert (
        client.post(
            "/api/auth/mfa/verify",
            json={
                "challenge_token": challenge,
                "code": result["recovery_codes"][0],
                "recovery": True,
            },
        ).status_code
        == 401
    )
    assert db.query(EventoSeguranca).filter_by(acao="RECUPERACAO_CODIGO").count() == 1


def test_sessao_final_pode_usar_cookie_httponly_e_logout_remove_cookie(
    client,
    db,
    usuario_factory,
):
    enroll(client, db, usuario_factory)

    autenticado = client.get("/api/auth/me")
    assert autenticado.status_code == 200

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_bloqueio_mfa_nao_reseta_com_senha(client, db, usuario_factory, monkeypatch):
    from app.routers import auth

    monkeypatch.setattr(auth, "MAX_LOGIN_ATTEMPTS", 2)
    u, secret, result = enroll(client, db, usuario_factory)
    challenge = client.post(
        "/api/auth/login",
        data={"username": u.username, "password": "Minha-frase-teste-2026"},
    ).json()["challenge_token"]
    for expected in [401, 423]:
        assert (
            client.post(
                "/api/auth/mfa/verify",
                json={"challenge_token": challenge, "code": "invalid"},
            ).status_code
            == expected
        )
    assert (
        client.post(
            "/api/auth/login",
            data={"username": u.username, "password": "Minha-frase-teste-2026"},
        ).status_code
        == 423
    )


def test_recuperacao_servidor_preserva_conta_e_revoga_sessao(
    client, db, usuario_factory
):
    u, _, result = enroll(client, db, usuario_factory)
    db.refresh(u)
    redefinir_acesso(db, u, hash_password("Temporaria-teste-2026"))
    db.commit()
    assert (
        client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer " + result["access_token"]},
        ).status_code
        == 401
    )
    assert not u.mfa_ativo and not u.recuperacao_hashes and u.senha_pendente
    assert db.query(EventoSeguranca).filter_by(acao="RECUPERACAO_SERVIDOR").count() == 1
    assert (
        client.post(
            "/api/auth/login",
            data={"username": u.username, "password": "Temporaria-teste-2026"},
        ).json()["action"]
        == "password"
    )


def test_token_antigo_e_expirado_nao_acessam(client, usuario_factory):
    u = usuario_factory("legado-token")
    for token in [
        create_access_token({"sub": str(u.id)}),
        create_access_token(
            {"sub": str(u.id), "purpose": "access", "ver": 0}, minutes=-1
        ),
    ]:
        assert (
            client.get(
                "/api/auth/me", headers={"Authorization": "Bearer " + token}
            ).status_code
            == 401
        )


def test_validacao_nao_reflete_segredos(client):
    response = client.post(
        "/api/auth/password",
        json={"challenge_token": "credencial-ficticia", "password": "curta"},
    )
    assert response.status_code == 422
    assert "credencial-ficticia" not in response.text and "curta" not in response.text


def test_recuperacao_pelo_comando_local(
    client, db, usuario_factory, testing_session_factory, monkeypatch
):
    from scripts import recover_account

    u, _, result = enroll(client, db, usuario_factory)
    prompts = iter([u.username, "RECUPERAR"])
    monkeypatch.setattr("builtins.input", lambda _: next(prompts))
    monkeypatch.setattr(recover_account, "getpass", lambda _: "Temporaria-comando-2026")
    monkeypatch.setattr(recover_account, "SessionLocal", testing_session_factory)
    assert recover_account.main() == 0
    assert (
        client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer " + result["access_token"]},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            data={"username": u.username, "password": "Temporaria-comando-2026"},
        ).json()["action"]
        == "password"
    )


def test_master_recupera_usuario_mas_nao_outro_master(
    client, db, usuario_factory, auth_headers
):
    master = usuario_factory("master-recuperador", role="ADMIN")
    u = usuario_factory("usuario-recuperado")
    antigo = auth_headers(u)
    response = client.patch(
        f"/api/usuarios/{u.id}/senha",
        headers=auth_headers(master),
        json={"password": "Temporaria-usuario-2026"},
    )
    assert response.status_code == 204
    assert client.get("/api/auth/me", headers=antigo).status_code == 401
    assert (
        client.patch(
            f"/api/usuarios/{master.id}/senha",
            headers=auth_headers(master),
            json={"password": "Temporaria-master-2026"},
        ).status_code
        == 403
    )


def test_admin_so_ve_proprio_historico(client, db, usuario_factory, auth_headers):
    from app.models import ConsultaHistorico

    admin = usuario_factory("admin-leitor", role="USUARIO")
    other = usuario_factory("outro-leitor")
    db.add(
        ConsultaHistorico(
            usuario_id=other.id,
            pergunta="Pergunta sintetica",
            resposta="Resposta sintetica",
            fonte_ids="[]",
        )
    )
    db.commit()
    assert (
        client.get("/api/consultar/historico", headers=auth_headers(admin)).json()[
            "total"
        ]
        == 0
    )


@pytest.mark.parametrize("role", ["USUARIO"])
def test_gestao_exclusiva_master(client, usuario_factory, auth_headers, role):
    u = usuario_factory("sem-gestao-" + role, role=role)
    headers = auth_headers(u)
    target = str(uuid.uuid4())
    checks = [
        ("GET", "/api/usuarios", None),
        ("GET", "/api/revisoes", None),
        ("DELETE", "/api/documentos/" + target, None),
        ("DELETE", "/api/consultar/historico/" + target, None),
        ("PATCH", "/api/documentos/" + target, {"titulo": "Alteracao proibida"}),
        (
            "PATCH",
            "/api/usuarios/" + target + "/senha",
            {"password": "Nova-senha-teste-2026"},
        ),
    ]
    for method, path, body in checks:
        assert (
            client.request(method, path, headers=headers, json=body).status_code == 403
        )
    assert (
        client.post(
            "/api/documentos",
            headers=headers,
            data={"titulo": "Teste", "tipo": "NORMA"},
            files={"arquivo": ("teste.txt", b"teste", "text/plain")},
        ).status_code
        == 403
    )


def test_atividade_autenticada_renova_sessao(client, usuario_factory, auth_headers):
    usuario = usuario_factory("sessao-deslizante")
    resposta = client.get("/api/auth/me", headers=auth_headers(usuario))
    assert resposta.status_code == 200
    token = resposta.headers.get("X-Access-Token")
    assert token
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == str(usuario.id)
    assert payload["role"] == "USUARIO"
