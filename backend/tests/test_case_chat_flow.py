"""Integração sintética do chat persistente da Análise; sem dados reais."""

import json
from uuid import UUID

import pytest
from app.models import Caso, CasoDocumento, CasoFato, CasoMensagem, CasoTarefa
from app.services import (
    case_chat_service,
    case_fact_extraction_service,
    case_ingestion_service,
    case_task_service,
)
from app.services.document_processor import ExtracaoDocumento, ParteExtraida


class RespostaOllama:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(
            {"response": "Resumo sintético para conferência humana."}
        ).encode()


@pytest.mark.parametrize(
    ("tipo_documento", "vinculo", "texto"),
    [
        ("RG_CNH", "TRANSMITENTE", "CNH fictícia de Pessoa Exemplo"),
        ("DOCUMENTO_PESSOAL", "ADQUIRENTE", "RG fictício de Pessoa Modelo"),
        ("CERTIDAO_CASAMENTO", "TRANSMITENTE", "Casamento fictício de duas pessoas"),
        ("CONTRATO_SOCIAL", "ADQUIRENTE", "Contrato social fictício e representação"),
        ("PROCURACAO", "ADQUIRENTE", "Procuração fictícia com poderes delimitados"),
        ("MATRICULA_IMOVEL", "IMOVEL", "Matrícula fictícia com averbação sintética"),
    ],
)
def test_chat_identifica_documento_e_parte_sem_publicar_no_corpus(
    client, db, usuario_factory, auth_headers, testing_session_factory,
    monkeypatch, tipo_documento, vinculo, texto,
):
    usuario = usuario_factory(f"doc-{tipo_documento.lower()}")
    caso = _criar_caso(db, usuario)
    _habilitar_banco_de_teste(monkeypatch, testing_session_factory)
    monkeypatch.setattr(
        case_ingestion_service, "extrair_documento",
        lambda _: ExtracaoDocumento([ParteExtraida(1, texto)]),
    )
    monkeypatch.setattr(
        case_fact_extraction_service, "_gerar_propostas", lambda _: {"fatos": []},
    )
    prompts = []

    def responder(requisicao, timeout):
        prompts.append(json.loads(requisicao.data.decode("utf-8"))["prompt"])
        return RespostaOllama()

    monkeypatch.setattr(case_chat_service.urllib.request, "urlopen", responder)
    resposta = client.post(
        f"/api/analises/casos/{caso.id}/documentos",
        headers=auth_headers(usuario),
        data={"tipo_documento": tipo_documento, "vinculo_ato": vinculo},
        files={"arquivo": ("exemplo.txt", texto.encode(), "text/plain")},
    )
    assert resposta.status_code == 202
    assert prompts
    assert f"tipo informado: {tipo_documento}" in prompts[0]
    assert f"parte/vínculo informado: {vinculo}" in prompts[0]
    assert texto in prompts[0]


def test_ocr_de_imagem_isolada_mantem_status_verificavel(tmp_path, monkeypatch):
    from app.routers.analyses import _validar_conteudo_arquivo
    from app.services import document_processor

    imagem = tmp_path / "documento-ficticio.png"
    imagem.write_bytes(b"\x89PNG\r\n\x1a\n" + b"imagem sintetica")
    assert _validar_conteudo_arquivo(imagem, ".png")
    monkeypatch.setattr(
        "app.services.local_ocr.ocr_imagem",
        lambda _: ("Certidão fictícia legível", True),
    )
    extracao = document_processor.extrair_documento(str(imagem), executar_ocr=True)
    assert extracao.situacao == "PROCESSADO_COMPLETO"
    assert extracao.partes[0].metodo == "OCR_LOCAL"


def _criar_caso(db, usuario):
    caso = Caso(
        titulo="Caso sintético de chat",
        identificacao="Processo de teste sintético",
        descricao="Descrição inicial sintética usada para contextualizar a análise.",
        tipo_ato="COMPRA_VENDA",
        criado_por=usuario.id,
        responsavel_id=usuario.id,
    )
    db.add(caso)
    db.commit()
    return caso


def _habilitar_banco_de_teste(monkeypatch, testing_session_factory):
    monkeypatch.setattr(case_chat_service, "SessionLocal", testing_session_factory)
    monkeypatch.setattr(case_task_service, "SessionLocal", testing_session_factory)


def test_upload_encadeia_extracao_a2_e_resposta_persistida(
    client,
    db,
    usuario_factory,
    auth_headers,
    testing_session_factory,
    monkeypatch,
):
    usuario = usuario_factory("chat-sintetico", role="ADMIN")
    caso = _criar_caso(db, usuario)
    _habilitar_banco_de_teste(monkeypatch, testing_session_factory)
    monkeypatch.setattr(
        case_ingestion_service,
        "extrair_documento",
        lambda _: ExtracaoDocumento(
            [ParteExtraida(1, "Nome: Pessoa Sintetica", situacao="EXTRAIDA")]
        ),
    )
    monkeypatch.setattr(
        case_fact_extraction_service,
        "_gerar_propostas",
        lambda _: {
            "fatos": [
                {
                    "campo": "nome",
                    "locus": "CORINGA",
                    "valor": "Pessoa Sintetica",
                    "estado_evidencia": "ENCONTRADO",
                    "trecho_fonte": "Nome: Pessoa Sintetica",
                }
            ]
        },
    )
    prompts = []

    def gerar_resposta(requisicao, timeout):
        prompts.append(json.loads(requisicao.data.decode("utf-8"))["prompt"])
        return RespostaOllama()

    monkeypatch.setattr(case_chat_service.urllib.request, "urlopen", gerar_resposta)

    response = client.post(
        f"/api/analises/casos/{caso.id}/documentos",
        headers=auth_headers(usuario),
        data={
            "tipo_documento": "CERTIDAO_CASAMENTO",
            "vinculo_ato": "TRANSMITENTE",
            "orientacao_usuario": "Confira os dados do casamento.",
        },
        files={
            "arquivo": (
                "certidao-sintetica.txt",
                b"Nome: Pessoa Sintetica",
                "text/plain",
            )
        },
    )

    assert response.status_code == 202
    assert "caminho_arquivo" not in response.json()
    documento = db.get(CasoDocumento, UUID(response.json()["id"]))
    assert documento.status == "PRONTO"
    assert documento.status_seguranca == "LIBERADO"
    assert documento.status_extracao_fatos == "PRONTO"

    mensagens = (
        db.query(CasoMensagem)
        .filter(CasoMensagem.caso_id == caso.id)
        .order_by(CasoMensagem.created_at.asc(), CasoMensagem.id.asc())
        .all()
    )
    assert [mensagem.papel for mensagem in mensagens] == ["USUARIO", "ASSISTENTE"]
    assert "Confira os dados do casamento" in mensagens[0].conteudo
    assert "Resumo sintético" in mensagens[1].conteudo
    assert "Pessoa Sintetica" in prompts[0]
    assert "Fato proposto" in prompts[0]
    assert "documento=certidao-sintetica.txt" in prompts[0]
    assert "vínculo=TRANSMITENTE" in prompts[0]
    assert "Data atual para comparação de prazos:" in prompts[0]
    assert (
        "Descrição inicial sintética usada para contextualizar a análise" in prompts[0]
    )
    assert "Processo de teste sintético" in prompts[0]

    fato = db.query(CasoFato).one()
    assert fato.estado_conferencia == "PENDENTE"
    assert fato.trecho_fonte == "Nome: Pessoa Sintetica"
    tarefas = db.query(CasoTarefa).filter(CasoTarefa.caso_id == caso.id).all()
    assert {tarefa.tipo for tarefa in tarefas} == {
        "EXTRACAO_DOCUMENTAL",
        "ANALISE_DOCUMENTO_CHAT",
        "EXTRACAO_FACTUAL_A2",
    }
    assert all(tarefa.status == "CONCLUIDA" for tarefa in tarefas)


def test_documento_que_precisa_de_ocr_nao_chega_ao_modelo(
    client,
    db,
    usuario_factory,
    auth_headers,
    testing_session_factory,
    monkeypatch,
):
    usuario = usuario_factory("chat-ocr-sintetico", role="ADMIN")
    caso = _criar_caso(db, usuario)
    _habilitar_banco_de_teste(monkeypatch, testing_session_factory)
    monkeypatch.setattr(
        case_ingestion_service,
        "extrair_documento",
        lambda _: ExtracaoDocumento([ParteExtraida(1, "", situacao="NECESSITA_OCR")]),
    )

    def nao_deve_gerar(*_args, **_kwargs):
        raise AssertionError("Documento sem texto não pode chegar ao Ollama.")

    monkeypatch.setattr(
        case_fact_extraction_service, "_gerar_propostas", nao_deve_gerar
    )
    monkeypatch.setattr(case_chat_service.urllib.request, "urlopen", nao_deve_gerar)

    response = client.post(
        f"/api/analises/casos/{caso.id}/documentos",
        headers=auth_headers(usuario),
        data={"tipo_documento": "OUTRO", "vinculo_ato": "ATO"},
        files={
            "arquivo": (
                "ocr-sintetico.txt",
                b"Arquivo sintetico sem camada de texto",
                "text/plain",
            )
        },
    )

    assert response.status_code == 202
    documento = db.get(CasoDocumento, UUID(response.json()["id"]))
    assert documento.status == "ERRO"
    assert documento.situacao_extracao == "NECESSITA_OCR"
    assert db.query(CasoFato).count() == 0
    mensagens = db.query(CasoMensagem).filter(CasoMensagem.caso_id == caso.id).all()
    assert [mensagem.papel for mensagem in mensagens] == ["USUARIO", "SISTEMA"]
    assert "OCR" in mensagens[-1].conteudo
    tarefa_chat = (
        db.query(CasoTarefa)
        .filter(
            CasoTarefa.caso_id == caso.id,
            CasoTarefa.tipo == "ANALISE_DOCUMENTO_CHAT",
        )
        .one()
    )
    assert tarefa_chat.status == "CONCLUIDA"


def test_caso_encerrado_reabre_sem_perder_historico(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    usuario = usuario_factory("chat-reabertura-sintetico")
    caso = _criar_caso(db, usuario)
    mensagem = CasoMensagem(
        caso_id=caso.id,
        papel="USUARIO",
        conteudo="Mensagem sintética preservada.",
        usuario_id=usuario.id,
    )
    db.add(mensagem)
    db.commit()
    headers = auth_headers(usuario)

    response = client.patch(
        f"/api/analises/casos/{caso.id}/status",
        headers=headers,
        json={"status": "ENCERRADO"},
    )
    assert response.status_code == 200

    response = client.patch(
        f"/api/analises/casos/{caso.id}/status",
        headers=headers,
        json={"status": "EM_PREPARACAO"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "EM_PREPARACAO"
    assert db.query(CasoMensagem).filter(CasoMensagem.caso_id == caso.id).count() == 1
