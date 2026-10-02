def test_admin_nao_pode_criar_outro_admin(
    client,
    usuario_factory,
    auth_headers,
):
    admin = usuario_factory("admin", role="USUARIO")
    resposta = client.post(
        "/api/usuarios",
        headers=auth_headers(admin),
        json={
            "nome": "Novo Admin",
            "username": "novo-admin",
            "password": "Senha-ficticia-4321",
            "role": "USUARIO",
        },
    )
    assert resposta.status_code == 403


def test_master_pode_criar_admin(
    client,
    usuario_factory,
    auth_headers,
):
    master = usuario_factory("master", role="ADMIN")
    resposta = client.post(
        "/api/usuarios",
        headers=auth_headers(master),
        json={
            "nome": "Novo Admin",
            "username": "novo-admin",
            "password": "Senha-ficticia-4321",
            "role": "USUARIO",
        },
    )
    assert resposta.status_code == 201
    assert resposta.json()["role"] == "USUARIO"


def test_usuario_comum_nao_lista_usuarios(
    client,
    usuario_factory,
    auth_headers,
):
    usuario = usuario_factory("comum")
    resposta = client.get("/api/usuarios", headers=auth_headers(usuario))
    assert resposta.status_code == 403
