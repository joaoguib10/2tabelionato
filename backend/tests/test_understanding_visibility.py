import pytest
from app.models import Documento, DocumentoChunk
from app.routers import documents
from app.services.semantic_search_service import buscar_chunks_semelhantes


@pytest.mark.parametrize(
    "alteracao",
    [
        {"situacao": "RASCUNHO"},
        {"situacao": "REVOGADO"},
        {"situacao": "ARQUIVADO"},
        {"ativo": False},
        {"status": "ERRO"},
        {"status": "PROCESSANDO"},
        {"status_seguranca": "REVISAO"},
    ],
)
def test_entendimento_nao_publicado_inacessivel_em_todas_rotas(
    client, db, usuario_factory, auth_headers, alteracao
):
    master = usuario_factory("master-visibilidade", role="ADMIN")
    usuario = usuario_factory("leitor-visibilidade")
    caminho = documents.UPLOAD_DIR / "entendimento.txt"
    caminho.write_text("Orientação sintética.", encoding="utf-8")
    valores = dict(
        titulo="Entendimento sintético",
        tipo="ENTENDIMENTO",
        situacao="APROVADO",
        ativo=True,
        status="PRONTO",
        status_seguranca="LIBERADO",
        nome_arquivo=caminho.name,
        caminho_arquivo=str(caminho),
        criado_por=master.id,
    )
    valores.update(alteracao)
    documento = Documento(**valores)
    db.add(documento)
    db.commit()
    for conta, esperado in ((usuario, 404), (master, 200)):
        headers = auth_headers(conta)
        for url in (
            f"/api/documentos/{documento.id}",
            f"/api/documentos/{documento.id}/download",
            f"/api/documentos/entendimentos/{documento.id}",
        ):
            assert client.get(url, headers=headers).status_code == esperado
        for url in ("/api/documentos", "/api/documentos/entendimentos"):
            assert client.get(url, headers=headers).json()["total"] == (
                1 if conta == master else 0
            )


def test_entendimentos_publicados_paginados(client, db, usuario_factory, auth_headers):
    usuario = usuario_factory("leitor-paginacao")
    for indice in range(105):
        db.add(
            Documento(
                titulo=f"Entendimento {indice}",
                tipo="ENTENDIMENTO",
                situacao="APROVADO",
                ativo=True,
                status="PRONTO",
                status_seguranca="LIBERADO",
                criado_por=usuario.id,
                nome_arquivo="sintetico.txt",
                caminho_arquivo="nao-utilizado",
            )
        )
    db.commit()
    vistos = set()
    for pagina in range(1, 7):
        resultado = client.get(
            f"/api/documentos/entendimentos?pagina={pagina}&por_pagina=20",
            headers=auth_headers(usuario),
        ).json()
        assert resultado["total"] == 105
        assert resultado["total_paginas"] == 6
        assert not vistos.intersection(item["id"] for item in resultado["items"])
        vistos.update(item["id"] for item in resultado["items"])
    assert len(vistos) == 105


def test_entendimento_publicado_alimenta_a_consulta_juridica(db, usuario_factory):
    admin = usuario_factory("admin-entendimento-rag", role="ADMIN")
    entendimento = Documento(
        titulo="Entendimento institucional sintético",
        tipo="ENTENDIMENTO",
        situacao="APROVADO",
        ativo=True,
        status="PRONTO",
        status_seguranca="LIBERADO",
        situacao_extracao="PROCESSADO_COMPLETO",
        criado_por=admin.id,
        nome_arquivo="entendimento.txt",
        caminho_arquivo="nao-utilizado",
    )
    db.add(entendimento)
    db.flush()
    db.add(
        DocumentoChunk(
            documento_id=entendimento.id,
            pagina=1,
            posicao=1,
            artigo="Art. 987",
            artigo_confirmado=True,
            conteudo="Art. 987 Entendimento sintético para homologação da consulta.",
        )
    )
    db.commit()
    resultados = buscar_chunks_semelhantes(db, "O que estabelece o Art. 987?", limite=3)
    assert len(resultados) == 1
    assert resultados[0]["documento_id"] == str(entendimento.id)
