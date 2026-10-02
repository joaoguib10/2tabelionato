"""A2 assistido: propostas locais, verificáveis e sempre pendentes."""

from uuid import UUID

import pytest
from app.models import Caso, CasoDocumento, CasoFato, Documento, DocumentoChunk
from app.services import case_fact_extraction_service as factual


@pytest.fixture
def master(usuario_factory):
    return usuario_factory("master-a2-assistido", role="ADMIN")


@pytest.fixture
def usuario(usuario_factory):
    return usuario_factory("usuario-a2-assistido")


def _caso_com_documento(client, db, master, auth_headers):
    caso = Caso(titulo="Caso A2 sintético", criado_por=master.id)
    db.add(caso)
    db.commit()
    response = client.post(
        f"/api/analises/casos/{caso.id}/documentos",
        headers=auth_headers(master),
        data={"tipo_documento": "OUTRO", "vinculo_ato": "ATO"},
        files={
            "arquivo": (
                "sintetico.txt",
                b"Nome declarado: Pessoa Sintetica. Valor declarado: 1000.",
                "text/plain",
            )
        },
    )
    assert response.status_code == 202
    documento = db.get(CasoDocumento, UUID(response.json()["id"]))
    return caso, documento


def test_proposta_cria_fato_pendente_com_trecho_verificavel(
    client,
    db,
    master,
    auth_headers,
    monkeypatch,
):
    caso, documento = _caso_com_documento(client, db, master, auth_headers)
    monkeypatch.setattr(
        factual,
        "_gerar_propostas",
        lambda _: {
            "fatos": [
                {
                    "campo": "nome",
                    "categoria": "pessoa",
                    "locus": "C",
                    "valor": "Pessoa Sintética",
                    "estado_evidencia": "ENCONTRADO",
                    "trecho_fonte": "Nome declarado: Pessoa Sintetica.",
                },
                {
                    "campo": "cpf",
                    "valor": "inventado",
                    "estado_evidencia": "ENCONTRADO",
                    "trecho_fonte": "CPF que não consta no documento",
                },
                {
                    "campo": "estado civil",
                    "valor": None,
                    "estado_evidencia": "AUSENTE",
                    "trecho_fonte": "Nome declarado: Pessoa Sintetica.",
                },
            ]
        },
    )
    response = client.post(
        f"/api/analises/casos/{caso.id}/documentos/{documento.id}/propor-fatos",
        headers=auth_headers(master),
    )
    assert response.status_code == 202
    db.refresh(documento)
    assert documento.status_extracao_fatos == "PRONTO"
    assert documento.diagnostico_extracao_fatos["propostas_criadas"] == 1
    assert (
        documento.diagnostico_extracao_fatos[
            "propostas_descartadas_sem_evidencia_verificavel"
        ]
        == 2
    )
    fato = db.query(CasoFato).one()
    assert fato.estado_conferencia == "PENDENTE"
    assert fato.proveniencia == "DOCUMENTAL"
    assert fato.metodo_extracao == "OLLAMA_LOCAL"
    assert fato.registrado_por is None
    assert fato.contexto["origem_registro"] == "PROPOSTA_IA"
    assert db.query(Documento).count() == 0
    assert db.query(DocumentoChunk).count() == 0


def test_proposta_e_idempotente_e_nao_sobrescreve_correcao_humana(
    client,
    db,
    master,
    auth_headers,
    monkeypatch,
):
    caso, documento = _caso_com_documento(client, db, master, auth_headers)
    monkeypatch.setattr(
        factual,
        "_gerar_propostas",
        lambda _: {
            "fatos": [
                {
                    "campo": "valor",
                    "categoria": "economico",
                    "locus": "E",
                    "valor": "1000",
                    "estado_evidencia": "ENCONTRADO",
                    "trecho_fonte": "Valor declarado: 1000.",
                }
            ]
        },
    )
    url = f"/api/analises/casos/{caso.id}/documentos/{documento.id}/propor-fatos"
    headers = auth_headers(master)
    assert client.post(url, headers=headers).status_code == 202
    fato = db.query(CasoFato).one()
    assert (
        client.post(
            f"/api/analises/casos/{caso.id}/fatos/{fato.id}/conferencias",
            headers=headers,
            json={"acao": "CORRIGIR", "valor_novo": "R$ 1.000,00"},
        ).status_code
        == 200
    )
    assert client.post(url, headers=headers).status_code == 409
    assert db.query(CasoFato).count() == 1
    db.refresh(fato)
    assert fato.valor_original == "1000"
    assert fato.valor_atual == "R$ 1.000,00"


def test_proposta_por_responsavel_exige_documento_elegivel(
    client,
    db,
    master,
    usuario,
    auth_headers,
    monkeypatch,
):
    caso, documento = _caso_com_documento(client, db, master, auth_headers)
    url = f"/api/analises/casos/{caso.id}/documentos/{documento.id}/propor-fatos"
    assert client.post(url, headers=auth_headers(usuario)).status_code == 404
    caso.responsavel_id = usuario.id
    documento.status_seguranca = "REVISAO"
    db.commit()
    assert client.post(url, headers=auth_headers(usuario)).status_code == 409
    documento.status_seguranca = "LIBERADO"
    db.commit()
    monkeypatch.setattr(factual, "OLLAMA_BASE_URL", "https://ollama.externo.invalid")
    assert client.post(url, headers=auth_headers(master)).status_code == 503


def test_falha_na_ia_e_publica_e_reprocessavel(
    client,
    db,
    master,
    auth_headers,
    monkeypatch,
):
    caso, documento = _caso_com_documento(client, db, master, auth_headers)

    def falhar(_):
        raise ValueError("segredo-interno-sintetico")

    monkeypatch.setattr(factual, "_gerar_propostas", falhar)
    url = f"/api/analises/casos/{caso.id}/documentos/{documento.id}/propor-fatos"
    assert client.post(url, headers=auth_headers(master)).status_code == 202
    db.refresh(documento)
    assert documento.status_extracao_fatos == "ERRO"
    assert "segredo-interno" not in documento.erro_extracao_fatos
    assert factual.reservar_extracao(documento.id)
    factual.liberar_extracao(documento.id)


def test_responsavel_libera_alerta_de_seguranca_com_auditoria(
    client,
    db,
    master,
    usuario,
    auth_headers,
):
    caso, documento = _caso_com_documento(client, db, master, auth_headers)
    documento.status_seguranca = "REVISAO"
    documento.alerta_seguranca = "Alerta sintético sem conteúdo sensível."
    caso.responsavel_id = usuario.id
    db.commit()
    url = f"/api/analises/casos/{caso.id}/documentos/{documento.id}/seguranca"
    assert (
        client.patch(
            url,
            headers=auth_headers(usuario),
            json={"acao": "LIBERAR"},
        ).status_code
        == 200
    )
    response = client.get(
        f"/api/analises/casos/{caso.id}/documentos/{documento.id}",
        headers=auth_headers(usuario),
    )
    assert response.status_code == 200
    assert response.json()["status_seguranca"] == "LIBERADO"
    assert response.json()["seguranca_liberada_por"] == str(usuario.id)
    assert response.json()["seguranca_liberada_em"] is not None
