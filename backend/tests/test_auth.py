from app.routers import auth as auth_router


def test_login_bloqueia_apos_maximo_de_tentativas(
    client,
    db,
    usuario_factory,
    monkeypatch,
):
    usuario = usuario_factory("ana")
    monkeypatch.setattr(auth_router, "MAX_LOGIN_ATTEMPTS", 3)

    for _ in range(2):
        resposta = client.post(
            "/api/auth/login",
            data={"username": "ana", "password": "9999"},
        )
        assert resposta.status_code == 401

    resposta = client.post(
        "/api/auth/login",
        data={"username": "ana", "password": "9999"},
    )
    assert resposta.status_code == 423

    db.refresh(usuario)
    assert usuario.tentativas_login == 3
    assert usuario.bloqueado_em is not None
    assert (
        client.post(
            "/api/auth/login",
            data={"username": "ana", "password": "1234"},
        ).status_code
        == 423
    )


def test_login_valida_senha_mas_exige_segundo_fator(
    client,
    db,
    usuario_factory,
):
    usuario = usuario_factory("bia")
    assert (
        client.post(
            "/api/auth/login",
            data={"username": "bia", "password": "senha"},
        ).status_code
        == 401
    )

    resposta = client.post(
        "/api/auth/login",
        data={"username": "bia", "password": "1234"},
    )
    assert resposta.status_code == 200
    assert resposta.json()["action"] == "verify"
    assert "access_token" not in resposta.json()
    db.refresh(usuario)
    assert usuario.tentativas_login == 0


def test_rota_protegida_rejeita_token_ausente(client):
    resposta = client.get("/api/auth/me")
    assert resposta.status_code == 401
