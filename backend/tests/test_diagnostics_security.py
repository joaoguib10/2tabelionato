def test_diagnostico_do_banco_exige_autenticacao(client):
    assert client.get("/api/database").status_code == 401
    assert client.get("/api/database/test").status_code == 401


def test_status_publico_nao_expoe_detalhes_do_banco(client):
    resposta = client.get("/api/status")

    assert resposta.status_code == 200
    assert resposta.json() == {
        "system": "Tabeleão",
        "backend": "online",
        "version": "0.1.0",
    }


def test_respostas_recebem_headers_de_hardening_e_request_id(client):
    resposta = client.get("/health", headers={"X-Request-ID": "teste-local-01"})

    assert resposta.status_code == 200
    assert resposta.headers["X-Request-ID"] == "teste-local-01"
    assert resposta.headers["X-Content-Type-Options"] == "nosniff"
    assert resposta.headers["X-Frame-Options"] == "DENY"
    assert resposta.headers["Referrer-Policy"] == "no-referrer"


def test_request_id_invalido_e_substituido(client):
    resposta = client.get("/health", headers={"X-Request-ID": "linha\ninjetada"})

    assert resposta.status_code == 200
    assert resposta.headers["X-Request-ID"] != "linha\ninjetada"


def test_ready_confirma_a_dependencia_do_banco(client):
    resposta = client.get("/ready")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ready", "database": "online"}
