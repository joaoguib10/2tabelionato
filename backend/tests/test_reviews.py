import uuid

import pytest
from app.models import ConsultaHistorico, ConsultaRevisao, Documento
from app.schemas import EntendimentoInternoCreate
from pydantic import ValidationError


def criar_consulta(db, usuario, resposta="Resposta original da IA."):
    consulta = ConsultaHistorico(
        usuario_id=usuario.id,
        pergunta="Pergunta controlada sem dados pessoais?",
        resposta=resposta,
        confianca=0.4,
        confiavel=False,
        situacao_resposta="EVIDENCIA_PARCIAL",
        fonte_ids="[]",
    )
    db.add(consulta)
    db.commit()
    db.refresh(consulta)
    return consulta


def avaliar_como_nao_util(client, auth_headers, usuario, consulta):
    return client.patch(
        f"/api/consultar/{consulta.id}/feedback",
        headers=auth_headers(usuario),
        json={
            "produtiva": False,
            "motivo": "RESPOSTA_INCOMPLETA",
            "comentario": "Requer conferência humana.",
        },
    )


def test_feedback_negativo_cria_revisao_idempotente(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    usuario = usuario_factory("revisao-idempotente")
    consulta = criar_consulta(db, usuario)

    assert (
        avaliar_como_nao_util(client, auth_headers, usuario, consulta).status_code
        == 204
    )
    assert (
        avaliar_como_nao_util(client, auth_headers, usuario, consulta).status_code
        == 204
    )

    revisoes = (
        db.query(ConsultaRevisao)
        .filter(ConsultaRevisao.consulta_id == consulta.id)
        .all()
    )
    assert len(revisoes) == 1
    assert revisoes[0].status == "PENDENTE"


def test_feedback_so_pode_ser_alterado_pelo_autor(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    autor = usuario_factory("autor-feedback")
    admin = usuario_factory("admin-nao-altera-feedback", role="USUARIO")
    consulta = criar_consulta(db, autor)

    resposta = client.patch(
        f"/api/consultar/{consulta.id}/feedback",
        headers=auth_headers(admin),
        json={"produtiva": False, "motivo": "RESPOSTA_INCOMPLETA"},
    )

    assert resposta.status_code == 403
    db.refresh(consulta)
    assert consulta.produtiva is None


def test_feedback_util_fecha_revisao_aberta_e_novo_negativo_reabre(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    usuario = usuario_factory("revisao-reaberta")
    consulta = criar_consulta(db, usuario)
    avaliar_como_nao_util(client, auth_headers, usuario, consulta)
    revisao = db.query(ConsultaRevisao).filter_by(consulta_id=consulta.id).one()

    util = client.patch(
        f"/api/consultar/{consulta.id}/feedback",
        headers=auth_headers(usuario),
        json={"produtiva": True},
    )
    assert util.status_code == 204
    db.refresh(revisao)
    assert revisao.status == "ENCERRADA"
    assert revisao.encerrada_em is not None

    avaliar_como_nao_util(client, auth_headers, usuario, consulta)
    db.refresh(revisao)
    assert revisao.status == "PENDENTE"
    assert revisao.encerrada_em is None


def test_entendimento_exige_metadados_minimos():
    with pytest.raises(ValidationError):
        EntendimentoInternoCreate(
            titulo="Entendimento",
            texto_generalizado="Orientação geral com conteúdo suficiente.",
            origem="   ",
            abrangencia="Serventia local",
            versao="1.0",
        )


def test_master_responde_e_usuario_ve_revisao_sem_perder_resposta_original(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    usuario = usuario_factory("autor-revisao")
    admin = usuario_factory("master-revisao", role="ADMIN")
    consulta = criar_consulta(db, usuario)
    resposta_original = consulta.resposta
    avaliar_como_nao_util(client, auth_headers, usuario, consulta)
    revisao = db.query(ConsultaRevisao).filter_by(consulta_id=consulta.id).one()

    proibida = client.get("/api/revisoes", headers=auth_headers(usuario))
    assert proibida.status_code == 403

    assumida = client.patch(
        f"/api/revisoes/{revisao.id}/status",
        headers=auth_headers(admin),
        json={"status": "EM_ANALISE"},
    )
    assert assumida.status_code == 200
    assert assumida.json()["responsavel_id"] == str(admin.id)

    resposta_humana = "Orientação revisada por responsável autorizado."
    respondida = client.post(
        f"/api/revisoes/{revisao.id}/resposta",
        headers=auth_headers(admin),
        json={"resposta_humana": resposta_humana},
    )
    assert respondida.status_code == 200
    assert respondida.json()["status"] == "RESPONDIDA"
    assert respondida.json()["resposta_ia"] == resposta_original

    historico = client.get(
        "/api/consultar/historico",
        headers=auth_headers(usuario),
    )
    assert historico.status_code == 200
    item = historico.json()["items"][0]
    assert item["resposta"] == resposta_original
    assert item["revisao"]["resposta_humana"] == resposta_humana
    assert item["revisao"]["respondido_por_nome"] == admin.nome
    assert item["revisao"]["respondido_por_role"] == "ADMIN"


def test_resposta_humana_nao_pode_ser_sobrescrita(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    usuario = usuario_factory("autor-resposta-preservada")
    admin = usuario_factory("master-resposta-inicial", role="ADMIN")
    master = usuario_factory("master-resposta-preservada", role="ADMIN")
    consulta = criar_consulta(db, usuario)
    avaliar_como_nao_util(client, auth_headers, usuario, consulta)
    revisao = db.query(ConsultaRevisao).filter_by(consulta_id=consulta.id).one()

    primeira = client.post(
        f"/api/revisoes/{revisao.id}/resposta",
        headers=auth_headers(admin),
        json={"resposta_humana": "Primeira orientação humana preservada."},
    )
    assert primeira.status_code == 200
    respondida_em = primeira.json()["respondida_em"]

    sobrescrita = client.post(
        f"/api/revisoes/{revisao.id}/resposta",
        headers=auth_headers(master),
        json={"resposta_humana": "Tentativa de substituir a orientação."},
    )
    assert sobrescrita.status_code == 409

    db.refresh(revisao)
    assert revisao.resposta_humana == "Primeira orientação humana preservada."
    assert revisao.respondido_por == admin.id
    assert revisao.respondida_em.isoformat() == respondida_em


def test_revisao_sem_resposta_nao_pode_ser_encerrada(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    usuario = usuario_factory("autor-revisao-sem-resposta")
    admin = usuario_factory("master-revisao-sem-resposta", role="ADMIN")
    consulta = criar_consulta(db, usuario)
    avaliar_como_nao_util(client, auth_headers, usuario, consulta)
    revisao = db.query(ConsultaRevisao).filter_by(consulta_id=consulta.id).one()

    resposta = client.patch(
        f"/api/revisoes/{revisao.id}/status",
        headers=auth_headers(admin),
        json={"status": "ENCERRADA"},
    )

    assert resposta.status_code == 409
    db.refresh(revisao)
    assert revisao.status == "PENDENTE"


def test_somente_master_transforma_e_aprova_entendimento(
    client,
    db,
    usuario_factory,
    auth_headers,
    monkeypatch,
    tmp_path,
):
    usuario = usuario_factory("autor-entendimento")
    admin = usuario_factory("admin-entendimento", role="USUARIO")
    master = usuario_factory("master-entendimento", role="ADMIN")
    consulta = criar_consulta(db, usuario)
    avaliar_como_nao_util(client, auth_headers, usuario, consulta)
    revisao = db.query(ConsultaRevisao).filter_by(consulta_id=consulta.id).one()
    client.post(
        f"/api/revisoes/{revisao.id}/resposta",
        headers=auth_headers(master),
        json={"resposta_humana": "Resposta humana específica para o caso."},
    )

    from app.routers import reviews

    monkeypatch.setattr(reviews, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(reviews, "processar_documento", lambda documento_id: None)
    dados = {
        "titulo": "Entendimento geral controlado",
        "texto_generalizado": (
            "Orientação geral redigida manualmente, sem reproduzir dados do caso original."
        ),
        "origem": "Revisão interna",
        "abrangencia": "Serventia local",
        "versao": "1.0",
        "observacao": "Sujeito à aprovação documental.",
    }

    proibida = client.post(
        f"/api/revisoes/{revisao.id}/entendimento",
        headers=auth_headers(admin),
        json=dados,
    )
    assert proibida.status_code == 403

    criada = client.post(
        f"/api/revisoes/{revisao.id}/entendimento",
        headers=auth_headers(master),
        json=dados,
    )
    assert criada.status_code == 201
    documento = db.get(Documento, uuid.UUID(criada.json()["id"]))
    assert documento is not None
    assert documento.tipo == "ENTENDIMENTO"
    assert documento.situacao == "RASCUNHO"
    assert documento.status == "PROCESSANDO"
    assert documento.orgao_origem == "Revisão interna"
    assert documento.jurisdicao == "Serventia local"
    assert documento.versao == "1.0"
    assert documento.observacoes == "Sujeito à aprovação documental."
    assert consulta.pergunta not in (tmp_path / documento.nome_arquivo).read_text(
        "utf-8"
    )
    db.refresh(revisao)
    assert revisao.entendimento_documento_id == documento.id

    documento.status = "PRONTO"
    documento.status_seguranca = "LIBERADO"
    db.commit()
    url_governanca = f"/api/documentos/{documento.id}/governanca"
    assert (
        client.patch(
            url_governanca,
            headers=auth_headers(admin),
            json={"situacao": "APROVADO"},
        ).status_code
        == 403
    )
    aprovada = client.patch(
        url_governanca,
        headers=auth_headers(master),
        json={"situacao": "APROVADO"},
    )
    assert aprovada.status_code == 200
    assert aprovada.json()["situacao"] == "APROVADO"
