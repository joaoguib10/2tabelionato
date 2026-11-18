import uuid

import pytest

from app.models import (
    Documento,
    DocumentoPagina,
    IAExternaConfiguracao,
    IAExternaFonte,
    IAExternaFila,
)
from app.routers import consultation as consultation_router
from app.routers import external_ai as external_ai_router
from app.services import external_ai_service


def _documento_aprovado(
    db, admin, *, liberacao_externa="LOCAL_ONLY", pagina_confiavel=True
):
    documento = Documento(
        titulo="Norma sintética de teste",
        tipo="NORMA",
        situacao="APROVADO",
        liberacao_externa=liberacao_externa,
        nome_arquivo="norma-sintetica.txt",
        caminho_arquivo="somente-teste",
        criado_por=admin.id,
        ativo=True,
        status="PRONTO",
        situacao_extracao="PROCESSADO_COMPLETO",
        status_seguranca="LIBERADO",
    )
    db.add(documento)
    db.flush()
    pagina = DocumentoPagina(
        documento_id=documento.id,
        pagina=1,
        pagina_confiavel=pagina_confiavel,
        localizacao="Página 1" if pagina_confiavel else "Bloco lógico 1",
        conteudo=(
            "A escritura pública deve identificar o solicitante e narrar os fatos "
            "de forma circunstanciada, com data e local do ato."
        ),
    )
    db.add(pagina)
    db.commit()
    return documento, pagina


def test_consulta_publica_segura_bloqueia_dados_e_contexto_de_caso():
    assert external_ai_service.consulta_publica_segura(
        "Quais são os requisitos gerais de uma escritura pública?"
    )
    assert external_ai_service.consulta_publica_segura(
        "Quais requisitos do Código Civil para Ata Notarial?"
    )
    assert not external_ai_service.consulta_publica_segura(
        "O que faço no meu processo de compra e venda?"
    )
    assert not external_ai_service.consulta_publica_segura(
        "João Silva pode vender para o próprio filho?"
    )
    assert not external_ai_service.consulta_publica_segura(
        "Confira o CPF 123.456.789-00"
    )


def test_store_institucional_e_chave_de_fila_sao_idempotentes(db):
    primeira = external_ai_service.obter_ou_criar_store_local(db)
    segunda = external_ai_service.obter_ou_criar_store_local(db)
    assert primeira.id == segunda.id

    job = IAExternaFila(
        acao="SINCRONIZAR_FONTE",
        status="CONCLUIDA",
        chave_idempotencia="sincronizacao-teste-versao-1",
        tentativas=4,
    )
    db.add(job)
    db.commit()
    reenfileirado = external_ai_service._enfileirar(
        db,
        acao="SINCRONIZAR_FONTE",
        chave="sincronizacao-teste-versao-1",
    )
    db.commit()
    assert reenfileirado.id == job.id
    assert reenfileirado.status == "PENDENTE"
    assert reenfileirado.tentativas == 0


def test_worker_processa_exclusoes_mesmo_com_consulta_desabilitada(
    db, testing_session_factory, monkeypatch
):
    db.add(IAExternaConfiguracao(chave="global", consulta_habilitada=False))
    job = IAExternaFila(
        acao="EXCLUIR_FONTE",
        status="PENDENTE",
        chave_idempotencia="exclusao-teste",
    )
    db.add(job)
    db.commit()
    monkeypatch.setattr(external_ai_service, "SessionLocal", testing_session_factory)
    monkeypatch.setattr(external_ai_service, "disponibilidade_externa", lambda: True)

    escolhido = external_ai_service._reivindicar_job()
    assert escolhido == job.id


def test_status_do_gateway_e_configuracao_sao_exclusivos_do_admin(
    client, usuario_factory, auth_headers
):
    usuario = usuario_factory("gateway-usuario")
    admin = usuario_factory("gateway-admin", role="ADMIN")
    assert client.get("/api/ia-externa/status", headers=auth_headers(usuario)).status_code == 403
    resposta = client.get("/api/ia-externa/status", headers=auth_headers(admin))
    assert resposta.status_code == 200
    assert "GEMINI_API_KEY" not in resposta.text
    assert "nome_remoto" not in resposta.text


@pytest.mark.parametrize("pagina_confiavel", [True, False])
def test_liberacao_de_documento_exige_admin_e_inspecao_local(
    client,
    db,
    usuario_factory,
    auth_headers,
    monkeypatch,
    pagina_confiavel,
):
    admin = usuario_factory("gateway-liberador", role="ADMIN")
    comum = usuario_factory("gateway-comum")
    documento, _ = _documento_aprovado(
        db, admin, pagina_confiavel=pagina_confiavel
    )
    db.add(IAExternaConfiguracao(chave="global", consulta_habilitada=True))
    db.commit()
    monkeypatch.setattr(external_ai_router, "disponibilidade_externa", lambda: True)

    url = f"/api/ia-externa/documentos/{documento.id}"
    payload = {
        "classificacao": "SINTETICO",
        "confirmou_politica_de_dados": True,
    }
    assert client.patch(url, json=payload, headers=auth_headers(comum)).status_code == 403

    resposta = client.patch(url, json=payload, headers=auth_headers(admin))
    assert resposta.status_code == 200
    assert resposta.json()["classificacao"] == "SINTETICO"
    fonte = db.query(IAExternaFonte).filter_by(documento_id=documento.id).one()
    assert fonte.status == "PENDENTE"
    assert fonte.tier == "DOCUMENTOS"
    db.expire_all()
    assert external_ai_service._conteudo_fonte_atual(db, fonte) is not None


def test_aprovacao_classifica_documento_de_consulta_como_publico(
    client, db, usuario_factory, auth_headers
):
    admin = usuario_factory("gateway-aprovacao", role="ADMIN")
    documento, _ = _documento_aprovado(db, admin)
    documento.situacao = "RASCUNHO"
    db.commit()

    resposta = client.patch(
        f"/api/documentos/{documento.id}/governanca",
        json={"situacao": "APROVADO"},
        headers=auth_headers(admin),
    )

    assert resposta.status_code == 200
    db.refresh(documento)
    assert documento.liberacao_externa == "PUBLICO"
    fonte = db.query(IAExternaFonte).filter_by(documento_id=documento.id).one()
    assert fonte.classificacao == "PUBLICO"
    assert fonte.status == "PENDENTE"


def test_reconciliacao_publica_documento_ja_aprovado(
    db, testing_session_factory, usuario_factory, monkeypatch
):
    admin = usuario_factory("gateway-reconciliacao", role="ADMIN")
    documento, _ = _documento_aprovado(db, admin)
    monkeypatch.setattr(external_ai_service, "SessionLocal", testing_session_factory)

    external_ai_service.reconciliar_documentos_publicos()

    db.refresh(documento)
    assert documento.liberacao_externa == "PUBLICO"
    assert db.query(IAExternaFonte).filter_by(documento_id=documento.id).count() == 1


def test_aprovacao_local_nao_depende_da_inspecao_externa(
    client, db, usuario_factory, auth_headers
):
    admin = usuario_factory("gateway-bloqueio", role="ADMIN")
    documento, pagina = _documento_aprovado(db, admin)
    documento.situacao = "RASCUNHO"
    pagina.conteudo = "Solicitante CPF 123.456.789-00."
    db.commit()

    resposta = client.patch(
        f"/api/documentos/{documento.id}/governanca",
        json={"situacao": "APROVADO"},
        headers=auth_headers(admin),
    )

    assert resposta.status_code == 200
    db.refresh(documento)
    assert documento.situacao == "APROVADO"
    assert documento.liberacao_externa == "LOCAL_ONLY"
    assert db.query(IAExternaFonte).filter_by(documento_id=documento.id).count() == 0


def test_norma_publica_exige_confirmacao_admin_para_excecao_de_inspecao(
    client, db, usuario_factory, auth_headers, monkeypatch
):
    admin = usuario_factory("norma-publica-admin", role="ADMIN")
    documento, pagina = _documento_aprovado(db, admin)
    pagina.conteudo = "Art. 1. Publicado no processo 12345/2026."
    db.add(IAExternaConfiguracao(chave="global", consulta_habilitada=True))
    db.commit()
    monkeypatch.setattr(external_ai_router, "disponibilidade_externa", lambda: True)
    url = f"/api/ia-externa/documentos/{documento.id}"
    payload = {"classificacao": "PUBLICO", "confirmou_politica_de_dados": True}

    assert client.patch(url, json=payload, headers=auth_headers(admin)).status_code == 409
    payload["confirmou_norma_publica_integral"] = True
    assert client.patch(url, json=payload, headers=auth_headers(admin)).status_code == 200
    db.refresh(documento)
    assert documento.liberacao_externa == "PUBLICO"
    fonte = db.query(IAExternaFonte).filter_by(documento_id=documento.id).one()
    assert external_ai_service._obter_conteudo_fonte(db, fonte) == pagina.conteudo

    documento.liberacao_externa = "LOCAL_ONLY"
    db.commit()
    with pytest.raises(ValueError, match="FONTE_LOCAL_DESATUALIZADA"):
        external_ai_service._obter_conteudo_fonte(db, fonte)


def test_excecao_publica_nao_serve_para_documento_fora_da_consulta_ou_vazio(
    client, db, usuario_factory, auth_headers, monkeypatch
):
    admin = usuario_factory("norma-limites-admin", role="ADMIN")
    documento, pagina = _documento_aprovado(db, admin)
    db.add(IAExternaConfiguracao(chave="global", consulta_habilitada=True))
    db.commit()
    monkeypatch.setattr(external_ai_router, "disponibilidade_externa", lambda: True)
    payload = {
        "classificacao": "PUBLICO",
        "confirmou_politica_de_dados": True,
        "confirmou_fonte_publica_integral": True,
    }
    url = f"/api/ia-externa/documentos/{documento.id}"
    documento.tipo = "OUTRO"
    db.commit()
    assert client.patch(url, json=payload, headers=auth_headers(admin)).status_code == 422
    documento.tipo = "NORMA"
    pagina.conteudo = "  "
    db.commit()
    assert client.patch(url, json=payload, headers=auth_headers(admin)).status_code == 409


def test_entendimento_publico_pode_ser_liberado_com_confirmacao_admin(
    client, db, usuario_factory, auth_headers, monkeypatch
):
    admin = usuario_factory("entendimento-publico-admin", role="ADMIN")
    comum = usuario_factory("entendimento-publico-comum")
    documento, pagina = _documento_aprovado(db, admin)
    documento.tipo = "ENTENDIMENTO"
    pagina.conteudo = "Checklist institucional. Processo 12345/2026."
    db.add(IAExternaConfiguracao(chave="global", consulta_habilitada=True))
    db.commit()
    monkeypatch.setattr(external_ai_router, "disponibilidade_externa", lambda: True)
    url = f"/api/ia-externa/documentos/{documento.id}"
    payload = {
        "classificacao": "PUBLICO",
        "confirmou_politica_de_dados": True,
        "confirmou_fonte_publica_integral": True,
    }
    assert client.patch(url, json=payload, headers=auth_headers(comum)).status_code == 403
    assert client.patch(url, json=payload, headers=auth_headers(admin)).status_code == 200
    db.expire_all()
    fonte = db.query(IAExternaFonte).filter_by(documento_id=documento.id).one()
    assert external_ai_service._obter_conteudo_fonte(db, fonte) == pagina.conteudo


def test_paginas_vazias_sao_ignoradas_sem_liberar_documento_vazio(
    client, db, usuario_factory, auth_headers, monkeypatch
):
    admin = usuario_factory("norma-pagina-vazia-admin", role="ADMIN")
    documento, _ = _documento_aprovado(db, admin)
    db.add(DocumentoPagina(documento_id=documento.id, pagina=2, conteudo="  "))
    db.add(IAExternaConfiguracao(chave="global", consulta_habilitada=True))
    db.commit()
    monkeypatch.setattr(external_ai_router, "disponibilidade_externa", lambda: True)
    resposta = client.patch(
        f"/api/ia-externa/documentos/{documento.id}",
        json={"classificacao": "PUBLICO", "confirmou_politica_de_dados": True},
        headers=auth_headers(admin),
    )
    assert resposta.status_code == 200
    assert db.query(IAExternaFonte).filter_by(documento_id=documento.id).count() == 1


def test_fonte_externa_so_e_validada_com_trecho_local_e_versao_atual(db, usuario_factory):
    admin = usuario_factory("gateway-citacao", role="ADMIN")
    documento, pagina = _documento_aprovado(db, admin, liberacao_externa="SINTETICO")
    store = external_ai_service.obter_ou_criar_store_local(db)
    fonte = IAExternaFonte(
        store_id=store.id,
        escopo="INSTITUCIONAL",
        tipo_fonte="DOCUMENTO",
        fonte_local_id=str(documento.id),
        documento_id=documento.id,
        tier="DOCUMENTOS",
        pagina=pagina.pagina,
        localizacao=pagina.localizacao,
        versao_hash=external_ai_service._hash_fonte(
            pagina.conteudo,
            f"{documento.id}||{documento.tipo}|{pagina.pagina}",
        ),
        classificacao="SINTETICO",
        nome_remoto=f"fonte-{uuid.uuid4().hex}",
        documento_remoto="stores/test/documents/approved",
        status="INDEXADO",
    )
    db.add(fonte)
    db.commit()
    trecho = pagina.conteudo[:75]
    interaction = {
        "output_text": "A escritura deve indicar o local e narrar os fatos.",
        "steps": [
            {
                "type": "model_output",
                "content": [
                    {
                        "type": "text",
                        "text": "A escritura deve indicar o local e narrar os fatos.",
                        "annotations": [
                            {
                                "type": "file_citation",
                                "file_name": fonte.nome_remoto,
                                "source": trecho,
                            }
                        ],
                    }
                ],
            }
        ],
    }

    texto, fontes = external_ai_service._obter_fontes_validas_da_resposta(
        db, interaction, {"DOCUMENTOS"}, "INSTITUCIONAL", None
    )
    assert texto == "A escritura deve indicar o local e narrar os fatos."
    assert len(fontes) == 1
    assert fontes[0]["documento_id"] == str(documento.id)
    assert fontes[0]["conteudo"] == trecho

    pagina.conteudo = "Texto diferente após reprocessamento da versão local."
    db.commit()
    _, fontes_desatualizadas = external_ai_service._obter_fontes_validas_da_resposta(
        db, interaction, {"DOCUMENTOS"}, "INSTITUCIONAL", None
    )
    assert fontes_desatualizadas == []


def test_consulta_externa_respeita_o_nivel_humano_prioritario(
    client,
    db,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    from app.models import DocumentoChunk

    admin = usuario_factory("gateway-prioridade-admin", role="ADMIN")
    usuario = usuario_factory("gateway-prioridade-usuario")
    documento = Documento(
        titulo="Entendimento sintético de compra e venda",
        tipo="ENTENDIMENTO",
        situacao="APROVADO",
        nome_arquivo="entendimento-sintetico.txt",
        caminho_arquivo="somente-teste",
        criado_por=admin.id,
        ativo=True,
        status="PRONTO",
        situacao_extracao="PROCESSADO_COMPLETO",
        status_seguranca="LIBERADO",
    )
    db.add(documento)
    db.flush()
    chunk = DocumentoChunk(
        documento_id=documento.id,
        pagina=1,
        posicao=1,
        conteudo="Na compra e venda, confira a titularidade do imóvel.",
    )
    db.add(chunk)
    db.commit()
    fonte = {
        "fonte_id": f"FONTE-{uuid.uuid4()}",
        "chunk_id": str(chunk.id),
        "documento_id": str(documento.id),
        "documento": documento.titulo,
        "versao_documento": None,
        "pagina": 1,
        "localizacao": "Bloco 1",
        "posicao": 1,
        "artigo": None,
        "artigo_contexto": None,
        "capitulo": None,
        "secao": None,
        "paragrafo": None,
        "inciso": None,
        "conteudo": chunk.conteudo,
        "similaridade": 0.0,
        "natureza_fonte": "Entendimento administrativo publicado",
    }
    niveis = []

    def consultar_tier(_db, _pergunta, tier, *, historico=""):
        niveis.append(tier)
        return "A titularidade deve ser conferida na matrícula.", [fonte]

    monkeypatch.setattr(consultation_router, "consultar_tier_externo", consultar_tier)
    monkeypatch.setattr(consultation_router, "disponibilidade_externa", lambda: True)
    monkeypatch.setattr(
        consultation_router,
        "_garantir_citacoes",
        lambda _resposta, _fontes, _pergunta: (
            "A titularidade deve ser conferida na matrícula.",
            [fonte["fonte_id"]],
            "EVIDENCIA_SUFFICIENTE",
        ),
    )
    monkeypatch.setattr(
        consultation_router, "_resposta_checklist_satisfatoria", lambda *_args: True
    )

    resposta = client.post(
        "/api/consultar",
        headers=auth_headers(usuario),
        json={"consulta": "O que conferir na compra e venda?"},
    )
    assert resposta.status_code == 200
    assert niveis == ["ENTENDIMENTO"]
    dados = resposta.json()
    assert dados["citacoes_verificadas"] == [fonte["fonte_id"]]

    feedback = client.patch(
        f"/api/consultar/{dados['id']}/feedback",
        headers=auth_headers(usuario),
        json={"produtiva": True},
    )
    assert feedback.status_code == 204
    historico = client.get(
        "/api/consultar/historico", headers=auth_headers(usuario)
    ).json()["items"]
    assert historico[0]["modelo_ia"] == consultation_router.GEMINI_MODEL
    assert historico[0]["parametros_ia"]["tier"] == "ENTENDIMENTO"
    assert historico[0]["fonte_ids"] == [fonte["fonte_id"]]
    assert historico[0]["fontes"][0]["trecho"] == chunk.conteudo
    assert historico[0]["produtiva"] is True


def test_consulta_externa_sem_evidencia_percorre_niveis_e_registra_limite(
    client, usuario_factory, auth_headers, monkeypatch
):
    usuario = usuario_factory("gateway-sem-evidencia")
    niveis = []

    def consultar_tier(_db, _pergunta, tier, *, historico=""):
        niveis.append(tier)
        return None

    monkeypatch.setattr(consultation_router, "consultar_tier_externo", consultar_tier)
    monkeypatch.setattr(consultation_router, "disponibilidade_externa", lambda: True)

    resposta = client.post(
        "/api/consultar",
        headers=auth_headers(usuario),
        json={"consulta": "Quais são os requisitos gerais da escritura pública?"},
    )

    assert resposta.status_code == 200
    assert niveis == ["ENTENDIMENTO", "REVISAO", "DOCUMENTOS"]
    assert resposta.json()["situacao_resposta"] == "BASE_INSUFICIENTE"
    assert resposta.json()["resultados"] == []


def test_consulta_com_identificador_nao_chama_gemini(
    client, usuario_factory, auth_headers, monkeypatch
):
    usuario = usuario_factory("gateway-dado-privado")
    monkeypatch.setattr(consultation_router, "disponibilidade_externa", lambda: True)
    monkeypatch.setattr(
        consultation_router,
        "consultar_tier_externo",
        lambda *_args, **_kwargs: pytest.fail("Não deve enviar identificador ao Gemini"),
    )

    resposta = client.post(
        "/api/consultar",
        headers=auth_headers(usuario),
        json={"consulta": "Confira o CPF 123.456.789-00 nesta escritura."},
    )

    assert resposta.status_code == 200
    assert resposta.json()["situacao_resposta"] == "BASE_INSUFICIENTE"
