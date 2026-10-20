"""Regressões para entradas hostis em campos que alimentam consultas SQL."""

from app.models import Usuario
from app.routers import consultation as consultation_router


def test_sql_injection_no_login_nao_autentica_usuario_existente(
    client,
    usuario_factory,
):
    usuario_factory("admin-sqli", role="ADMIN", pin="1234")

    resposta = client.post(
        "/api/auth/login",
        data={
            "username": "admin-sqli' OR '1'='1' --",
            "password": "1234",
        },
    )

    assert resposta.status_code == 401
    assert "access_token" not in resposta.json()


def test_sql_injection_na_consulta_nao_altera_o_banco(
    client,
    db,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("consulta-sqli")
    monkeypatch.setattr(
        consultation_router,
        "buscar_chunks_semelhantes",
        lambda *args, **kwargs: [],
    )
    pergunta = "x'; DROP TABLE usuarios; --"

    resposta = client.post(
        "/api/consultar",
        headers=auth_headers(usuario),
        json={"consulta": pergunta, "historico": []},
    )

    assert resposta.status_code == 200
    assert resposta.json()["situacao_resposta"] == "BASE_INSUFICIENTE"
    assert db.query(Usuario).filter(Usuario.id == usuario.id).count() == 1
