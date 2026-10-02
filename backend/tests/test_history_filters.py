from app.models import ConsultaHistorico


def criar_consulta(
    db, usuario, indice: int, produtiva=None, situacao="EVIDENCIA_SUFFICIENTE"
):
    registro = ConsultaHistorico(
        usuario_id=usuario.id,
        pergunta=f"Pergunta controlada {indice}",
        resposta="Resposta sem dados pessoais.",
        confianca=0.5,
        confiavel=situacao == "EVIDENCIA_SUFFICIENTE",
        situacao_resposta=situacao,
        fonte_ids="[]",
        produtiva=produtiva,
    )
    db.add(registro)
    return registro


def test_historico_respeita_usuario_e_filtros_administrativos(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    usuario_a = usuario_factory("historico-a")
    usuario_b = usuario_factory("historico-b")
    admin = usuario_factory("historico-master", role="ADMIN")
    criar_consulta(db, usuario_a, 1, True)
    criar_consulta(db, usuario_b, 2, False, "BASE_INSUFICIENTE")
    db.commit()

    proprio = client.get(
        "/api/consultar/historico",
        headers=auth_headers(usuario_a),
    ).json()
    assert proprio["total"] == 1
    assert proprio["items"][0]["usuario_username"] == "historico-a"

    filtrado = client.get(
        f"/api/consultar/historico?usuario_id={usuario_b.id}&avaliacao=NAO_UTIL",
        headers=auth_headers(admin),
    ).json()
    assert filtrado["total"] == 1
    assert filtrado["items"][0]["usuario_nome"] == "Historico-B"
    assert filtrado["items"][0]["situacao_resposta"] == "BASE_INSUFICIENTE"


def test_historico_tem_paginacao_real(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    usuario = usuario_factory("historico-paginado")
    for indice in range(25):
        criar_consulta(db, usuario, indice)
    db.commit()
    pagina = client.get(
        "/api/consultar/historico?pagina=2&por_pagina=20",
        headers=auth_headers(usuario),
    ).json()
    assert pagina["total"] == 25
    assert pagina["pagina"] == 2
    assert len(pagina["items"]) == 5


def test_feedback_negativo_aceita_motivo_e_comentario(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    usuario = usuario_factory("feedback-detalhado")
    registro = criar_consulta(db, usuario, 1)
    db.commit()
    resposta = client.patch(
        f"/api/consultar/{registro.id}/feedback",
        headers=auth_headers(usuario),
        json={
            "produtiva": False,
            "motivo": "RESPOSTA_INCOMPLETA",
            "comentario": "Faltou indicar uma exceção.",
        },
    )
    assert resposta.status_code == 204
    db.refresh(registro)
    assert registro.feedback_motivo == "RESPOSTA_INCOMPLETA"
    assert registro.feedback_comentario == "Faltou indicar uma exceção."


def test_apenas_master_exclui_registro_do_historico(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    usuario = usuario_factory("historico-exclusao")
    admin = usuario_factory("historico-exclusao-admin", role="USUARIO")
    master = usuario_factory("historico-exclusao-master", role="ADMIN")

    registro_admin = criar_consulta(db, usuario, 1)
    registro_master = criar_consulta(db, usuario, 2)
    db.commit()
    registro_admin_id = registro_admin.id
    registro_master_id = registro_master.id

    proibida = client.delete(
        f"/api/consultar/historico/{registro_admin_id}",
        headers=auth_headers(usuario),
    )
    assert proibida.status_code == 403
    assert db.get(ConsultaHistorico, registro_admin_id) is not None

    excluida_admin = client.delete(
        f"/api/consultar/historico/{registro_admin_id}",
        headers=auth_headers(admin),
    )
    assert excluida_admin.status_code == 403
    db.expire_all()
    assert db.get(ConsultaHistorico, registro_admin_id) is not None

    excluida_master = client.delete(
        f"/api/consultar/historico/{registro_master_id}",
        headers=auth_headers(master),
    )
    assert excluida_master.status_code == 204
    db.expire_all()
    assert db.get(ConsultaHistorico, registro_master_id) is None
