"""Regressões pré-A2: somente dados sintéticos e arquivos temporários."""

from pathlib import Path
from uuid import UUID

import pytest
from app.models import (
    Caso,
    CasoConferencia,
    CasoDocumento,
    CasoDocumentoPagina,
    CasoFato,
    Documento,
    DocumentoChunk,
    DocumentoPagina,
)
from app.schemas import CasoDocumentoClassificacaoUpdate
from app.services import case_ingestion_service as ingestion
from app.services.document_processor import ExtracaoDocumento, ParteExtraida


@pytest.fixture
def caso(db, usuario_factory):
    dono = usuario_factory("dono-sintetico")
    caso = Caso(titulo="Caso sintético", criado_por=dono.id, responsavel_id=dono.id)
    db.add(caso)
    db.commit()
    return caso, dono


@pytest.fixture
def master(usuario_factory):
    return usuario_factory("master-sintetico", role="ADMIN")


def upload(client, caso, headers):
    return client.post(
        f"/api/analises/casos/{caso.id}/documentos",
        headers=headers,
        files={
            "arquivo": (
                "sintetico.txt",
                b"Conteudo sintetico privado do caso.",
                "text/plain",
            )
        },
    )


def test_visibilidade_casos_proprios_atribuidos_e_master(
    client, db, caso, master, usuario_factory, auth_headers
):
    registro, dono = caso
    atribuido = usuario_factory("atribuido-sintetico")
    terceiro = usuario_factory("terceiro-sintetico")
    registro.responsavel_id = atribuido.id
    db.commit()
    for usuario in (dono, atribuido, master):
        headers = auth_headers(usuario)
        assert (
            client.get(
                f"/api/analises/casos/{registro.id}", headers=headers
            ).status_code
            == 200
        )
        assert client.get("/api/analises/casos", headers=headers).json()["total"] == 1
    headers = auth_headers(terceiro)
    assert (
        client.get(f"/api/analises/casos/{registro.id}", headers=headers).status_code
        == 404
    )
    assert client.get("/api/analises/casos", headers=headers).json()["total"] == 0


@pytest.mark.parametrize(
    "destino", ["PRONTO_PARA_ANALISE", "ANALISE_DISPONIVEL", "DECISAO_REGISTRADA"]
)
def test_nao_antecipa_etapas_futuras(client, db, caso, master, auth_headers, destino):
    registro, dono = caso
    registro.status = {
        "PRONTO_PARA_ANALISE": "AGUARDANDO_CONFERENCIA",
        "ANALISE_DISPONIVEL": "PRONTO_PARA_ANALISE",
        "DECISAO_REGISTRADA": "ANALISE_DISPONIVEL",
    }[destino]
    db.commit()
    anterior = registro.status
    response = client.patch(
        f"/api/analises/casos/{registro.id}/status",
        headers=auth_headers(master),
        json={"status": destino},
    )
    assert response.status_code == 409
    db.refresh(registro)
    assert registro.status == anterior


def test_preparacao_conferencia_e_encerramento_preservados(
    client, caso, master, auth_headers
):
    registro, dono = caso
    for destino in ("AGUARDANDO_CONFERENCIA", "EM_PREPARACAO", "ENCERRADO"):
        response = client.patch(
            f"/api/analises/casos/{registro.id}/status",
            headers=auth_headers(master),
            json={"status": destino},
        )
        assert response.status_code == 200
        assert response.json()["status"] == destino


def test_ingestao_privada_nao_cria_corpus_e_preserva_paginas(
    client, db, caso, master, auth_headers, monkeypatch
):
    registro, dono = caso
    monkeypatch.setattr(
        ingestion,
        "extrair_documento",
        lambda _: ExtracaoDocumento(
            [
                ParteExtraida(1, "Primeiro bloco sintético."),
                ParteExtraida(2, "Segundo bloco sintético."),
            ]
        ),
    )
    response = upload(client, registro, auth_headers(master))
    assert response.status_code == 202
    doc_id = UUID(response.json()["id"])
    assert "caminho_arquivo" not in response.json()
    documento = db.get(CasoDocumento, doc_id)
    assert documento.status == "PRONTO"
    assert documento.total_paginas == 2
    assert (
        db.query(CasoDocumentoPagina).filter_by(caso_documento_id=doc_id).count() == 2
    )
    for model in (Documento, DocumentoPagina, DocumentoChunk):
        assert db.query(model).count() == 0
    assert upload(client, registro, auth_headers(master)).status_code == 409
    assert db.query(CasoDocumento).count() == 1


def test_anexos_inacessiveis_por_outro_usuario_ou_caso(
    client, db, caso, master, usuario_factory, auth_headers
):
    registro, dono = caso
    terceiro = usuario_factory("outro-dono")
    outro = Caso(
        titulo="Outro caso", criado_por=terceiro.id, responsavel_id=terceiro.id
    )
    db.add(outro)
    db.commit()
    response = upload(client, registro, auth_headers(master))
    assert response.status_code == 202
    doc_id = response.json()["id"]
    headers = auth_headers(terceiro)
    assert upload(client, registro, headers).status_code == 404
    for alvo in (registro, outro):
        base = f"/api/analises/casos/{alvo.id}/documentos/{doc_id}"
        for metodo, caminho, json in (
            ("GET", base, None),
            ("GET", base + "/download", None),
            ("DELETE", base, None),
            ("POST", base + "/reprocessar", None),
            ("PATCH", base + "/classificacao", {"tipo_documento": "OUTRO"}),
        ):
            resposta = client.request(metodo, caminho, headers=headers, json=json)
            assert resposta.status_code in {403, 404}
    # O UUID do anexo privado também não existe no acervo institucional.
    assert (
        client.get(
            f"/api/documentos/{doc_id}/download", headers=auth_headers(dono)
        ).status_code
        == 404
    )


def test_reprocessamento_recupera_interrupcao_e_nao_duplica_paginas(
    client, db, caso, master, auth_headers
):
    registro, dono = caso
    headers = auth_headers(master)
    response = upload(client, registro, headers)
    doc_id = UUID(response.json()["id"])
    documento = db.get(CasoDocumento, doc_id)
    documento.status = "PROCESSANDO"  # Simula servidor interrompido, sem tarefa ativa.
    db.commit()
    url = f"/api/analises/casos/{registro.id}/documentos/{doc_id}/reprocessar"
    assert ingestion.reservar_processamento(doc_id)
    assert client.post(url, headers=headers).status_code == 409
    ingestion.liberar_processamento(doc_id)
    for _ in range(2):
        assert client.post(url, headers=headers).status_code == 202
        db.refresh(documento)
        assert documento.status == "PRONTO"
        assert (
            db.query(CasoDocumentoPagina).filter_by(caso_documento_id=doc_id).count()
            == 1
        )


def test_erro_publico_nao_expoe_detalhe_interno_e_permite_tentar_novamente(
    client, db, caso, master, auth_headers, monkeypatch
):
    registro, dono = caso

    def falhar(_):
        raise ValueError("detalhe-interno-sintetico")

    monkeypatch.setattr(ingestion, "extrair_documento", falhar)
    response = upload(client, registro, auth_headers(master))
    doc_id = UUID(response.json()["id"])
    documento = db.get(CasoDocumento, doc_id)
    assert documento.status == "ERRO"
    assert "detalhe-interno" not in documento.erro_processamento
    assert ingestion.reservar_processamento(
        doc_id
    )  # Reserva foi liberada mesmo na falha.
    ingestion.liberar_processamento(doc_id)


def test_casos_paginados_e_classificacao_nao_constitui_fatos(
    client, db, caso, master, auth_headers
):
    registro, dono = caso
    for indice in range(21):
        db.add(Caso(titulo=f"Caso adicional {indice}", criado_por=dono.id))
    db.commit()
    headers = auth_headers(master)
    primeira = client.get("/api/analises/casos", headers=headers).json()
    segunda = client.get("/api/analises/casos?pagina=2", headers=headers).json()
    assert primeira["total"] == 22
    assert len(primeira["items"]) == 20
    assert len(segunda["items"]) == 2
    documento = upload(client, registro, headers).json()
    response = client.patch(
        f"/api/analises/casos/{registro.id}/documentos/{documento['id']}/classificacao",
        headers=headers,
        json={"tipo_documento": "OUTRO"},
    )
    assert response.status_code == 200
    assert (
        client.get(f"/api/analises/casos/{registro.id}", headers=headers).json()[
            "total_fatos"
        ]
        == 0
    )


@pytest.mark.parametrize("tipo", ["ATA", "ESTATUTO", "REGIMENTO"])
def test_documentos_de_representacao_institucional_sao_aceitos(tipo):
    dados = CasoDocumentoClassificacaoUpdate(tipo_documento=tipo, vinculo_ato="ATO")
    assert dados.tipo_documento == tipo


@pytest.mark.parametrize("bloqueio", ["encerrado", "fatos", "arquivo_ausente"])
def test_reprocessamento_respeita_integridade(
    client, db, caso, master, auth_headers, bloqueio
):
    registro, dono = caso
    headers = auth_headers(master)
    doc_id = UUID(upload(client, registro, headers).json()["id"])
    documento = db.get(CasoDocumento, doc_id)
    if bloqueio == "encerrado":
        registro.status = "ENCERRADO"
    elif bloqueio == "fatos":
        db.add(
            CasoFato(
                caso_id=registro.id,
                caso_documento_id=doc_id,
                campo="campo-sintetico",
                proveniencia="DOCUMENTAL",
            )
        )
    else:
        documento.caminho_arquivo = str(
            Path(documento.caminho_arquivo).with_name("ausente.txt")
        )
    db.commit()
    response = client.post(
        f"/api/analises/casos/{registro.id}/documentos/{doc_id}/reprocessar",
        headers=headers,
    )
    assert response.status_code == (404 if bloqueio == "arquivo_ausente" else 409)
    db.refresh(documento)
    assert documento.status == "PRONTO"
    assert (
        db.query(CasoDocumentoPagina).filter_by(caso_documento_id=doc_id).count() == 1
    )


def test_usuario_trabalha_no_proprio_caso_e_admin_controla_atribuicao(
    client, db, caso, master, usuario_factory, auth_headers
):
    registro, dono = caso
    atribuido = usuario_factory("atribuido-pelo-master")
    terceiro = usuario_factory("terceiro-sem-acesso")
    headers_usuario = auth_headers(dono)
    assert (
        client.post(
            "/api/analises/casos",
            headers=headers_usuario,
            json={"titulo": "Caso do usuário"},
        ).status_code
        == 201
    )
    assert (
        client.patch(
            f"/api/analises/casos/{registro.id}",
            headers=headers_usuario,
            json={"titulo": "Atualizado pelo proprietário"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/analises/casos/{registro.id}/fatos",
            headers=headers_usuario,
            json={"campo": "nome", "valor": "Sintético", "proveniencia": "DECLARADA"},
        ).status_code
        == 201
    )
    assert (
        client.patch(
            f"/api/analises/casos/{registro.id}/responsavel",
            headers=headers_usuario,
            json={"responsavel_id": str(atribuido.id)},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/analises/casos/{registro.id}",
            headers=auth_headers(terceiro),
            json={"titulo": "Sem acesso"},
        ).status_code
        == 404
    )

    response = client.patch(
        f"/api/analises/casos/{registro.id}/responsavel",
        headers=auth_headers(master),
        json={"responsavel_id": str(atribuido.id)},
    )
    assert response.status_code == 200
    assert response.json()["responsavel_id"] == str(atribuido.id)
    assert (
        client.get(
            f"/api/analises/casos/{registro.id}", headers=auth_headers(atribuido)
        ).status_code
        == 200
    )


def test_a2_manual_preserva_original_e_historico_append_only(
    client, db, caso, master, auth_headers
):
    registro, _ = caso
    headers = auth_headers(master)
    response = client.post(
        f"/api/analises/casos/{registro.id}/fatos",
        headers=headers,
        json={
            "campo": "estado civil",
            "categoria": "pessoa",
            "locus": "C",
            "valor": "solteiro",
            "proveniencia": "DECLARADA",
            "estado_evidencia": "INCERTO",
        },
    )
    assert response.status_code == 201
    fato_id = response.json()["id"]
    assert response.json()["valor_original"] == "solteiro"
    assert response.json()["estado_conferencia"] == "PENDENTE"
    assert (
        client.post(
            f"/api/analises/casos/{registro.id}/fatos/{fato_id}/conferencias",
            headers=headers,
            json={
                "acao": "CORRIGIR",
                "valor_novo": "casado",
                "observacao": "Conferência sintética.",
            },
        ).status_code
        == 200
    )
    fato = db.get(CasoFato, UUID(fato_id))
    assert fato.valor_original == "solteiro"
    assert fato.valor_atual == "casado"
    assert fato.estado_conferencia == "CORRIGIDO"
    assert (
        client.post(
            f"/api/analises/casos/{registro.id}/fatos/{fato_id}/conferencias",
            headers=headers,
            json={"acao": "REABRIR"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/analises/casos/{registro.id}/fatos/{fato_id}/conferencias",
            headers=headers,
            json={"acao": "REABRIR", "observacao": "Novo elemento sintético."},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/analises/casos/{registro.id}/fatos/{fato_id}/conferencias",
            headers=headers,
            json={"acao": "CONFIRMAR"},
        ).status_code
        == 200
    )
    historico = client.get(
        f"/api/analises/casos/{registro.id}/fatos/{fato_id}/conferencias",
        headers=headers,
    ).json()
    assert historico["total"] == 3
    assert [item["acao"] for item in historico["items"]] == [
        "CORRIGIR",
        "REABRIR",
        "CONFIRMAR",
    ]
    assert db.query(CasoConferencia).count() == 3


def test_fato_documental_exige_documento_e_pagina_do_mesmo_caso(
    client, db, caso, master, usuario_factory, auth_headers
):
    registro, _ = caso
    headers = auth_headers(master)
    doc_id = UUID(upload(client, registro, headers).json()["id"])
    outro_dono = usuario_factory("dono-documento-externo")
    outro_caso = Caso(titulo="Caso externo sintético", criado_por=outro_dono.id)
    db.add(outro_caso)
    db.flush()
    externo = CasoDocumento(
        caso_id=outro_caso.id,
        nome_arquivo="externo.txt",
        caminho_arquivo="externo",
        status="PRONTO",
        criado_por=master.id,
    )
    db.add(externo)
    db.commit()
    base = {"campo": "nome", "valor": "Pessoa sintética", "proveniencia": "DOCUMENTAL"}
    assert (
        client.post(
            f"/api/analises/casos/{registro.id}/fatos", headers=headers, json=base
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/analises/casos/{registro.id}/fatos",
            headers=headers,
            json={**base, "caso_documento_id": str(externo.id)},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/analises/casos/{registro.id}/fatos",
            headers=headers,
            json={**base, "caso_documento_id": str(doc_id), "pagina": 99},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/analises/casos/{registro.id}/fatos",
            headers=headers,
            json={**base, "caso_documento_id": str(doc_id), "pagina": 1, "locus": "C"},
        ).status_code
        == 201
    )


def test_gate_para_analise_exige_processamento_e_conferencia(
    client, db, caso, master, auth_headers
):
    registro, _ = caso
    headers = auth_headers(master)
    registro.status = "AGUARDANDO_CONFERENCIA"
    db.commit()
    url_status = f"/api/analises/casos/{registro.id}/status"
    assert (
        client.patch(
            url_status, headers=headers, json={"status": "PRONTO_PARA_ANALISE"}
        ).status_code
        == 409
    )
    fato = client.post(
        f"/api/analises/casos/{registro.id}/fatos",
        headers=headers,
        json={
            "campo": "fato sintético",
            "valor": "preservado",
            "proveniencia": "DECLARADA",
        },
    ).json()
    assert (
        client.patch(
            url_status, headers=headers, json={"status": "PRONTO_PARA_ANALISE"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/analises/casos/{registro.id}/fatos/{fato['id']}/conferencias",
            headers=headers,
            json={"acao": "CONFIRMAR"},
        ).status_code
        == 200
    )
    pronto = client.patch(
        url_status, headers=headers, json={"status": "PRONTO_PARA_ANALISE"}
    )
    assert pronto.status_code == 200
    assert pronto.json()["status"] == "PRONTO_PARA_ANALISE"
    reaberto = client.post(
        f"/api/analises/casos/{registro.id}/fatos/{fato['id']}/conferencias",
        headers=headers,
        json={"acao": "REABRIR", "observacao": "Mudança sintética."},
    )
    assert reaberto.status_code == 200
    db.refresh(registro)
    assert registro.status == "AGUARDANDO_CONFERENCIA"
