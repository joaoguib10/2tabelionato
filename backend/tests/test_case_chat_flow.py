"""Integração sintética do chat persistente da Análise; sem dados reais."""

import json
from uuid import UUID, uuid4

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
    assert f"vínculo informado: {vinculo}" in prompts[0]
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
    assert "vínculo informado: TRANSMITENTE" in prompts[0]
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


def test_chat_nao_confunde_falha_a2_com_falha_de_leitura(
    client,
    db,
    usuario_factory,
    auth_headers,
    testing_session_factory,
    monkeypatch,
):
    usuario = usuario_factory("chat-sem-bloqueio-a2", role="ADMIN")
    caso = _criar_caso(db, usuario)
    _habilitar_banco_de_teste(monkeypatch, testing_session_factory)
    texto_extraido = "Comprovante fictício de endereço residencial."
    monkeypatch.setattr(
        case_ingestion_service,
        "extrair_documento",
        lambda _: ExtracaoDocumento([ParteExtraida(1, texto_extraido)]),
    )

    def falha_a2_nao_deve_bloquear_chat(*_args, **_kwargs):
        raise AssertionError("O modo conversacional não deve aguardar a extração A2.")

    monkeypatch.setattr(
        case_fact_extraction_service,
        "_gerar_propostas",
        falha_a2_nao_deve_bloquear_chat,
    )
    prompts = []

    def responder(requisicao, timeout):
        prompts.append(json.loads(requisicao.data.decode("utf-8"))["prompt"])
        return RespostaOllama()

    monkeypatch.setattr(case_chat_service.urllib.request, "urlopen", responder)

    upload = client.post(
        f"/api/analises/casos/{caso.id}/documentos",
        headers=auth_headers(usuario),
        data={
            "tipo_documento": "CONTRATO_SOCIAL",
            "vinculo_ato": "ADQUIRENTE",
            "responder_apos_processamento": "false",
        },
        files={"arquivo": ("documento-legivel.txt", texto_extraido.encode(), "text/plain")},
    )
    assert upload.status_code == 202
    documento_id = upload.json()["id"]
    documento = db.get(CasoDocumento, UUID(documento_id))
    assert documento.status == "PRONTO"
    assert documento.situacao_extracao == "PROCESSADO_COMPLETO"
    assert db.query(CasoTarefa).filter(CasoTarefa.tipo == "EXTRACAO_FACTUAL_A2").count() == 0
    mensagem_upload = (
        db.query(CasoMensagem)
        .filter(CasoMensagem.caso_id == caso.id, CasoMensagem.papel == "USUARIO")
        .one()
    )
    assert "Arquivo anexado ao processo." in mensagem_upload.conteudo
    assert "Faça a leitura factual" not in mensagem_upload.conteudo
    assert not prompts
    db.add(
        CasoMensagem(
            caso_id=caso.id,
            papel="USUARIO",
            conteudo=(
                "Analise em conjunto todos os documentos legíveis e liberados deste processo, "
                "inclusive os arquivos enviados agora. Compare o conteúdo real.\n\n"
                "Se algum arquivo estiver com extração parcial, ilegível, bloqueado "
                "ou sem texto, identifique nominalmente esse arquivo."
            ),
        )
    )
    db.commit()

    gerar = client.post(
        f"/api/analises/casos/{caso.id}/mensagens?gerar=true",
        headers=auth_headers(usuario),
        json={
            "conteudo": (
                "Confira se o conteúdo real corresponde ao tipo de documento "
                "informado e analise os arquivos legíveis do caso."
            )
        },
    )
    assert gerar.status_code == 201
    assert len(prompts) == 1
    assert texto_extraido in prompts[0]
    assert "Diferencie sempre o estado técnico do arquivo" in prompts[0]
    assert "tratar de assunto ou pessoa diferente do esperado" in prompts[0]
    assert "O documento foi extraído e está disponível para leitura" not in prompts[0]
    assert "Analise em conjunto todos os documentos legíveis e liberados" not in prompts[0]
    assert db.query(CasoFato).count() == 0


def test_falha_a2_nao_impede_resposta_do_chat_com_documento_pronto(
    client,
    db,
    usuario_factory,
    auth_headers,
    testing_session_factory,
    monkeypatch,
):
    usuario = usuario_factory("chat-a2-com-falha", role="ADMIN")
    caso = _criar_caso(db, usuario)
    _habilitar_banco_de_teste(monkeypatch, testing_session_factory)
    texto_extraido = "Contrato fictício com cláusula de administração legível."
    monkeypatch.setattr(
        case_ingestion_service,
        "extrair_documento",
        lambda _: ExtracaoDocumento([ParteExtraida(1, texto_extraido)]),
    )

    def falha_a2(*_args, **_kwargs):
        raise RuntimeError("falha simulada da extração factual")

    monkeypatch.setattr(case_fact_extraction_service, "_gerar_propostas", falha_a2)
    prompts = []

    def responder(requisicao, timeout):
        prompts.append(json.loads(requisicao.data.decode("utf-8"))["prompt"])
        return RespostaOllama()

    monkeypatch.setattr(case_chat_service.urllib.request, "urlopen", responder)

    upload = client.post(
        f"/api/analises/casos/{caso.id}/documentos",
        headers=auth_headers(usuario),
        data={
            "tipo_documento": "CONTRATO_SOCIAL",
            "vinculo_ato": "ADQUIRENTE",
        },
        files={"arquivo": ("contrato-sintetico.txt", texto_extraido.encode(), "text/plain")},
    )

    assert upload.status_code == 202
    documento = db.get(CasoDocumento, UUID(upload.json()["id"]))
    assert documento.status == "PRONTO"
    assert documento.status_extracao_fatos == "ERRO"
    assert len(prompts) == 1
    assert texto_extraido in prompts[0]
    mensagens = (
        db.query(CasoMensagem)
        .filter(CasoMensagem.caso_id == caso.id)
        .order_by(CasoMensagem.created_at.asc(), CasoMensagem.id.asc())
        .all()
    )
    assert any(mensagem.papel == "ASSISTENTE" for mensagem in mensagens)
    mensagem_status = next(
        mensagem.conteudo for mensagem in mensagens if mensagem.papel == "SISTEMA"
    )
    assert "está disponível para leitura" in mensagem_status
    assert "leitura do arquivo falhou" in mensagem_status
    assert "não consegui extrair texto" not in mensagem_status


def test_chat_analisa_texto_disponivel_de_extracao_parcial(
    client,
    db,
    usuario_factory,
    auth_headers,
    testing_session_factory,
    monkeypatch,
):
    usuario = usuario_factory("chat-extracao-parcial", role="ADMIN")
    caso = _criar_caso(db, usuario)
    _habilitar_banco_de_teste(monkeypatch, testing_session_factory)
    texto_legivel = "Matrícula fictícia: R.3 registra aquisição pela parte indicada."
    monkeypatch.setattr(
        case_ingestion_service,
        "extrair_documento",
        lambda _: ExtracaoDocumento(
            [
                ParteExtraida(1, texto_legivel),
                ParteExtraida(2, "", situacao="NECESSITA_OCR"),
            ]
        ),
    )
    prompts = []

    def responder(requisicao, timeout):
        prompts.append(json.loads(requisicao.data.decode("utf-8"))["prompt"])
        return RespostaOllama()

    monkeypatch.setattr(case_chat_service.urllib.request, "urlopen", responder)

    upload = client.post(
        f"/api/analises/casos/{caso.id}/documentos",
        headers=auth_headers(usuario),
        data={
            "tipo_documento": "MATRICULA_IMOVEL",
            "vinculo_ato": "IMOVEL",
            "responder_apos_processamento": "false",
        },
        files={"arquivo": ("matricula-parcial.txt", b"arquivo sintetico", "text/plain")},
    )
    assert upload.status_code == 202
    documento = db.get(CasoDocumento, UUID(upload.json()["id"]))
    assert documento.status == "PRONTO"
    assert documento.situacao_extracao == "EXTRACAO_PARCIAL"

    gerar = client.post(
        f"/api/analises/casos/{caso.id}/mensagens?gerar=true",
        headers=auth_headers(usuario),
        json={"conteudo": "Faça a análise inicial do processo."},
    )
    assert gerar.status_code == 201
    assert len(prompts) == 1
    assert texto_legivel in prompts[0]
    assert "EXTRACAO_PARCIAL" in prompts[0]


def test_analise_geral_reune_documentos_de_todo_o_processo(
    client,
    db,
    usuario_factory,
    auth_headers,
    testing_session_factory,
    monkeypatch,
):
    usuario = usuario_factory("chat-processo-integral", role="ADMIN")
    caso = _criar_caso(db, usuario)
    _habilitar_banco_de_teste(monkeypatch, testing_session_factory)
    documentos_sinteticos = [
        (
            "CERTIDAO_CASAMENTO",
            "TRANSMITENTE",
            "certidao-vendedores.txt",
            "Certidão fictícia: Pessoa Exemplo casada com Pessoa Modelo.",
        ),
        (
            "PROCURACAO",
            "ADQUIRENTE",
            "procuracao-comprador.txt",
            "Procuração fictícia: poderes de representação da Pessoa Compradora.",
        ),
        (
            "MATRICULA_IMOVEL",
            "IMOVEL",
            "matricula-imovel.txt",
            "Matrícula fictícia: titularidade e averbação para análise.",
        ),
        (
            "CONTRATO_SOCIAL",
            "ADQUIRENTE",
            "contrato-social-sintetico.txt",
            "Sociedade Modelo Ltda. CNPJ 00.000.000/0001-00. Cláusula 8: a sócia Ana Exemplo, administradora, pode representar a sociedade e assinar contratos individualmente.",
        ),
    ]
    textos_extraidos = iter(item[3] for item in documentos_sinteticos)
    monkeypatch.setattr(
        case_ingestion_service,
        "extrair_documento",
        lambda _: ExtracaoDocumento([ParteExtraida(1, next(textos_extraidos))]),
    )
    monkeypatch.setattr(
        case_fact_extraction_service, "_gerar_propostas", lambda _: {"fatos": []}
    )
    prompts = []

    def capturar_prompt(requisicao, timeout):
        prompts.append(json.loads(requisicao.data.decode("utf-8"))["prompt"])
        return RespostaOllama()

    monkeypatch.setattr(case_chat_service.urllib.request, "urlopen", capturar_prompt)

    for tipo, vinculo, nome_arquivo, conteudo in documentos_sinteticos:
        response = client.post(
            f"/api/analises/casos/{caso.id}/documentos",
            headers=auth_headers(usuario),
            data={
                "tipo_documento": tipo,
                "vinculo_ato": vinculo,
                "orientacao_usuario": (
                    "Faça a análise geral do processo e relacione os documentos."
                ),
            },
            files={"arquivo": (nome_arquivo, conteudo.encode(), "text/plain")},
        )
        assert response.status_code == 202

    assert len(prompts) == len(documentos_sinteticos)
    prompt_analise_geral = prompts[-1]
    prompt_normalizado = " ".join(prompt_analise_geral.split())
    for tipo, vinculo, nome_arquivo, conteudo in documentos_sinteticos:
        assert nome_arquivo in prompt_analise_geral
        assert conteudo in prompt_analise_geral
        assert f"tipo informado: {tipo}" in prompt_analise_geral
        assert f"vínculo informado: {vinculo}" in prompt_analise_geral
    assert "síntese do conjunto" in prompt_normalizado
    assert "o que cada arquivo trata" in prompt_normalizado
    assert "titularidade e averbação" in prompt_analise_geral
    assert "Não negue um poder que esteja escrito" in prompt_analise_geral
    assert "informe que aquele ônus foi cancelado/baixado" in prompt_normalizado
    assert (
        "remova qualquer pendência que já esteja expressamente resolvida"
        in prompt_normalizado
    )
    assert (
        "Não peça prova de que o proprietário autorizou a própria alienação"
        in prompt_analise_geral
    )
    assert (
        "não atribua ao representante a obrigação de representar o alienante"
        in prompt_normalizado
    )
    assert "ROTEIRO OPERACIONAL DE COMPRA E VENDA" in prompt_analise_geral
    assert "prazo operacional de 90 dias" in prompt_normalizado
    assert "emissão há no máximo 30 dias" in prompt_normalizado
    assert "peça matrícula atualizada como pendência" in prompt_normalizado
    assert "Devolutiva — documentos e informações pendentes" in prompt_analise_geral
    assert "um documento ou informação por linha" in prompt_normalizado
    assert "Não declare ausência de pendências" in prompt_normalizado
    assert "Junta Comercial competente" in prompt_analise_geral
    assert "contratar consigo mesmo" in prompt_normalizado
    assert "forma de pagamento, valor e datas" in prompt_normalizado
    assert "Sociedade Modelo Ltda." in prompt_analise_geral
    assert "Ana Exemplo, administradora" in prompt_analise_geral

    mensagens = (
        db.query(CasoMensagem)
        .filter(CasoMensagem.caso_id == caso.id)
        .order_by(CasoMensagem.created_at.asc(), CasoMensagem.id.asc())
        .all()
    )
    assert sum(mensagem.papel == "ASSISTENTE" for mensagem in mensagens) == 4
    assert "Resumo sintético" in mensagens[-1].conteudo


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


def test_lote_de_documentos_inicia_analise_no_servidor(
    client,
    db,
    usuario_factory,
    auth_headers,
    testing_session_factory,
    monkeypatch,
):
    usuario = usuario_factory("lote-sintetico")
    caso = _criar_caso(db, usuario)
    _habilitar_banco_de_teste(monkeypatch, testing_session_factory)
    monkeypatch.setattr(
        case_ingestion_service,
        "extrair_documento",
        lambda _: ExtracaoDocumento([ParteExtraida(1, "Documento sintético do caso")]),
    )
    monkeypatch.setattr(
        case_fact_extraction_service, "_gerar_propostas", lambda _: {"fatos": []}
    )

    upload = client.post(
        f"/api/analises/casos/{caso.id}/documentos",
        headers=auth_headers(usuario),
        data={
            "tipo_documento": "MATRICULA_IMOVEL",
            "vinculo_ato": "IMOVEL",
            "responder_apos_processamento": "false",
        },
        files={
            "arquivo": (
                "matricula-sintetica.txt",
                b"Synthetic case document",
                "text/plain",
            )
        },
    )
    assert upload.status_code == 202
    documento_id = UUID(upload.json()["id"])

    def concluir_sem_modelo(mensagem_id, tarefa_id):
        sessao = testing_session_factory()
        try:
            mensagem = sessao.get(CasoMensagem, mensagem_id)
            assert mensagem is not None
            tarefa = sessao.get(CasoTarefa, tarefa_id)
            assert tarefa is not None and tarefa.tipo == "ANALISE_LOTE"
            sessao.add(
                CasoMensagem(
                    caso_id=mensagem.caso_id,
                    papel="ASSISTENTE",
                    conteudo="Devolutiva sintética do processo.",
                )
            )
            tarefa.status = "CONCLUIDA"
            sessao.commit()
        finally:
            sessao.close()

    monkeypatch.setattr(
        case_chat_service, "processar_mensagem_caso", concluir_sem_modelo
    )
    analise = client.post(
        f"/api/analises/casos/{caso.id}/analisar-lote",
        headers=auth_headers(usuario),
        json={
            "documento_ids": [str(documento_id)],
            "conteudo": "Documentação anexada para análise.",
        },
    )
    assert analise.status_code == 202
    assert analise.json()["conteudo"] == "Documentação anexada para análise."
    assert db.query(CasoTarefa).filter_by(tipo="ANALISE_LOTE").one().status == "CONCLUIDA"
    respostas = (
        db.query(CasoMensagem)
        .filter(CasoMensagem.caso_id == caso.id, CasoMensagem.papel == "ASSISTENTE")
        .all()
    )
    assert [item.conteudo for item in respostas] == [
        "Devolutiva sintética do processo."
    ]


def test_lote_nao_aceita_documento_de_outro_caso(
    client, db, usuario_factory, auth_headers
):
    usuario = usuario_factory("lote-acesso")
    caso = _criar_caso(db, usuario)
    resposta = client.post(
        f"/api/analises/casos/{caso.id}/analisar-lote",
        headers=auth_headers(usuario),
        json={
            "documento_ids": [str(uuid4())],
            "conteudo": "Documentação anexada para análise.",
        },
    )
    assert resposta.status_code == 404


def test_analise_inicial_amplia_a_busca_sem_alterar_a_mensagem_visivel():
    mensagem = "Documentação anexada para análise."
    assert case_chat_service._pergunta_para_recuperacao(mensagem, False) == mensagem
    busca = case_chat_service._pergunta_para_recuperacao(mensagem, True)
    assert "matrícula imóvel proprietário" in busca
    assert "contrato social alteração administrador" in busca
    assert busca.endswith(f"Orientação do escrevente: {mensagem}")
