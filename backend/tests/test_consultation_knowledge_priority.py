import uuid
from types import SimpleNamespace

import pytest
from app.models import (
    ConsultaFonte,
    ConsultaHistorico,
    ConsultaRevisao,
    Documento,
    DocumentoChunk,
    DocumentoPagina,
    utc_now,
)
from app.routers import consultation as consultation_router
from app.services.consultation_knowledge_service import (
    _filtro_candidatos_entendimento,
    buscar_entendimentos_publicados,
    buscar_respostas_revisadas_admin,
)
from sqlalchemy import select
from sqlalchemy.dialects import postgresql


def _adicionar_entendimento(db, autor, *, titulo, conteudo, situacao="APROVADO"):
    documento = Documento(
        titulo=titulo,
        tipo="ENTENDIMENTO",
        situacao=situacao,
        ativo=True,
        status="PRONTO",
        status_seguranca="LIBERADO",
        situacao_extracao="PROCESSADO_COMPLETO",
        nome_arquivo="entendimento-sintetico.txt",
        caminho_arquivo="nao-utilizado",
        criado_por=autor.id,
    )
    db.add(documento)
    db.flush()
    chunk = DocumentoChunk(
        documento_id=documento.id,
        pagina=1,
        posicao=1,
        conteudo=conteudo,
    )
    db.add(chunk)
    db.commit()
    db.refresh(documento)
    db.refresh(chunk)
    return documento, chunk


def _adicionar_revisao(db, usuario, admin, *, pergunta, resposta, status="RESPONDIDA"):
    consulta = ConsultaHistorico(
        usuario_id=usuario.id,
        pergunta=pergunta,
        resposta="Resposta inicial sintética.",
    )
    db.add(consulta)
    db.flush()
    revisao = ConsultaRevisao(
        consulta_id=consulta.id,
        status=status,
        resposta_humana=resposta,
        respondido_por=admin.id,
        respondida_em=utc_now(),
    )
    db.add(revisao)
    db.commit()
    db.refresh(revisao)
    return consulta, revisao


def test_entendimentos_pesquisados_por_palavras_chave_e_governanca(db, usuario_factory):
    admin = usuario_factory("admin-palavras-chave", role="ADMIN")
    aprovado, _ = _adicionar_entendimento(
        db,
        admin,
        titulo="Checklist de Compra e Venda",
        conteudo=(
            "Na compra e venda, o vendedor apresenta matrícula atualizada e "
            "comprova a titularidade do imóvel."
        ),
    )
    _adicionar_entendimento(
        db,
        admin,
        titulo="Checklist de Doação",
        conteudo="A doação exige conferir a qualificação do doador e do donatário.",
    )
    _adicionar_entendimento(
        db,
        admin,
        titulo="Checklist de Compra e Venda em rascunho",
        conteudo="Rascunho não publicado para compra e venda.",
        situacao="RASCUNHO",
    )

    fontes = buscar_entendimentos_publicados(
        db, "Quais documentos são necessários para compra e venda?"
    )

    assert fontes
    assert all(item["documento_id"] == str(aprovado.id) for item in fontes)
    assert fontes[0]["natureza_fonte"] == "Entendimento administrativo publicado"


def test_busca_humana_separa_o_ato_e_tolera_erro_em_termo_generico(
    db, usuario_factory
):
    admin = usuario_factory("admin-busca-por-ato", role="ADMIN")
    compra_venda, _ = _adicionar_entendimento(
        db,
        admin,
        titulo="Checklist Compra e Venda",
        conteudo="Compra e venda: conferir vendedor, comprador e matrícula.",
    )
    inventario, _ = _adicionar_entendimento(
        db,
        admin,
        titulo="Checklist Inventário",
        conteudo=(
            "No inventário, conferir herdeiros, partilha e os bens. "
            "A venda de bens depende de autorização específica."
        ),
    )

    fontes_compra_venda = buscar_entendimentos_publicados(
        db, "O que é necessário para Escritura de Compra e Venda?"
    )
    fontes_inventario = buscar_entendimentos_publicados(
        db, "O que é necessário para Escriturda de Inventário?"
    )

    assert fontes_compra_venda
    assert {item["documento_id"] for item in fontes_compra_venda} == {
        str(compra_venda.id)
    }
    assert fontes_inventario
    assert {item["documento_id"] for item in fontes_inventario} == {
        str(inventario.id)
    }


def test_busca_humana_nao_depende_de_lista_fechada_de_atos(db, usuario_factory):
    admin = usuario_factory("admin-ato-dinamico", role="ADMIN")
    documento, _ = _adicionar_entendimento(
        db,
        admin,
        titulo="Orientação sobre Dação em Pagamento",
        conteudo=(
            "Na dação em pagamento de imóvel, confira a titularidade, o valor e "
            "a forma de extinção da obrigação."
        ),
    )

    fontes = buscar_entendimentos_publicados(
        db, "Quais documentos são necessários para Dação em Pagamento?"
    )

    assert fontes
    assert {item["documento_id"] for item in fontes} == {str(documento.id)}


def test_busca_postgresql_compila_full_text_em_portugues_sem_dependencia_de_acentos():
    class SessaoPostgreSQL:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    filtro, relevancia = _filtro_candidatos_entendimento(
        "Dissolucao de Uniao Estavel", SessaoPostgreSQL()
    )
    consulta = (
        select(DocumentoChunk.id)
        .join(Documento, Documento.id == DocumentoChunk.documento_id)
        .where(filtro)
        .order_by(relevancia.desc())
        .compile(dialect=postgresql.dialect())
    )

    assert "to_tsvector('portuguese', translate(documento_chunks.conteudo" in str(
        consulta
    )
    assert "coalesce(documentos.titulo, '')" in str(consulta)
    assert "plainto_tsquery('portuguese'" in str(consulta)
    assert "dissolucao" in consulta.params.values()


def test_filtro_de_palavras_aplicado_antes_do_limite_de_candidatos(
    db, usuario_factory, monkeypatch
):
    admin = usuario_factory("admin-filtro-antes-limite", role="ADMIN")
    irrelevante, _ = _adicionar_entendimento(
        db,
        admin,
        titulo="Manual de administração interna",
        conteudo="Procedimentos de expediente e organização administrativa.",
    )
    relevante, _ = _adicionar_entendimento(
        db,
        admin,
        titulo="Checklist de Dissolução de União Estável",
        conteudo=(
            "Para dissolução de união estável, apresentar documentos pessoais e "
            "certidão atualizada de estado civil."
        ),
    )
    irrelevante.aprovado_em = utc_now().replace(year=2099)
    db.commit()
    monkeypatch.setattr(
        "app.services.consultation_knowledge_service.MAX_CHUNKS_ENTENDIMENTOS", 1
    )

    fontes = buscar_entendimentos_publicados(
        db, "O que preciso para Dissolução de União Estável?"
    )

    assert fontes
    assert {item["documento_id"] for item in fontes} == {str(relevante.id)}


def test_consulta_resume_checklist_humano_compacto_sem_buscar_documentos(
    client,
    db,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("consulta-checklist-humano")
    admin = usuario_factory("admin-checklist-humano", role="ADMIN")
    compra_venda, _ = _adicionar_entendimento(
        db,
        admin,
        titulo="Checklist Compra e Venda",
        conteudo=(
            "Vendedor: documento pessoal e CPF; certidão de estado civil atualizada. "
            "Comprador: documento pessoal e CPF; comprovante de endereço."
        ),
    )
    _adicionar_entendimento(
        db,
        admin,
        titulo="Checklist Inventário",
        conteudo=(
            "Inventário: certidão de óbito, documentos dos herdeiros e relação de bens. "
            "A venda de bens depende de condição específica."
        ),
    )
    db.add(
        DocumentoPagina(
            documento_id=compra_venda.id,
            pagina=1,
            conteudo=(
                "Vendedor: documento pessoal e CPF; certidão de estado civil atualizada. "
                "Comprador: documento pessoal e CPF; comprovante de endereço."
            ),
        )
    )
    db.commit()
    chamadas = []

    def gerar_resumo(**kwargs):
        chamadas.append(kwargs)
        assert kwargs["resumir_checklist"] is True
        assert "certidão de estado civil atualizada" in kwargs["contexto"].casefold()
        return (
            "Na compra e venda, confira a identificação e o CPF das partes, a "
            "certidão atualizada de estado civil do vendedor e o comprovante de "
            "endereço do comprador. [FONTE-1]"
        )

    def busca_documental_proibida(*_args, **_kwargs):
        pytest.fail("A consulta deveria responder pelo entendimento publicado.")

    monkeypatch.setattr(consultation_router, "gerar_resposta", gerar_resumo)
    monkeypatch.setattr(
        consultation_router,
        "buscar_chunks_semelhantes",
        busca_documental_proibida,
    )

    resposta = client.post(
        "/api/consultar",
        headers=auth_headers(usuario),
        json={"consulta": "O que é necessário para Escritura de Compra e Venda?"},
    )

    assert resposta.status_code == 200
    dados = resposta.json()
    assert len(chamadas) == 1
    assert dados["situacao_resposta"] == "EVIDENCIA_SUFFICIENTE"
    assert "certidão atualizada de estado civil do vendedor" in dados["resposta"]
    assert all(
        fonte["documento"] == "Checklist Compra e Venda"
        for fonte in dados["resultados"]
    )


def test_entendimento_integral_nao_depende_do_formato_da_pergunta():
    pergunta = "Na compra e venda, como verifico a titularidade do imóvel?"
    assert not consultation_router._pergunta_pede_requisitos_gerais(pergunta)
    fonte = {
        "conteudo": "Item completo do checklist " * 20,
        "documento": "Checklist administrativo",
        "natureza_fonte": "Entendimento administrativo publicado",
        "pagina": 1,
        "localizacao": None,
        "capitulo": None,
        "secao": None,
        "paragrafo": None,
        "inciso": None,
        "artigo": None,
    }

    with pytest.raises(consultation_router.ContextoCompletoExcedido):
        consultation_router._montar_contexto([fonte], limite=100, exigir_completo=True)


def test_respostas_de_revisao_exigem_resposta_de_admin_e_nao_expoem_pergunta(
    db, usuario_factory
):
    usuario = usuario_factory("usuario-revisao-chave")
    admin = usuario_factory("admin-revisao-chave", role="ADMIN")
    _, respondida = _adicionar_revisao(
        db,
        usuario,
        admin,
        pergunta="Quais documentos são necessários para compra e venda?",
        resposta=(
            "Na compra e venda, confira a matrícula atualizada e a prova de "
            "titularidade do imóvel."
        ),
    )
    _adicionar_revisao(
        db,
        usuario,
        admin,
        pergunta="Quais documentos são necessários para compra e venda?",
        resposta="Resposta ainda pendente.",
        status="PENDENTE",
    )
    _, resposta_com_dado_pessoal = _adicionar_revisao(
        db,
        usuario,
        admin,
        pergunta="Quais documentos são necessários para compra e venda?",
        resposta="A matrícula de CPF 123.456.789-00 precisa ser conferida.",
    )
    usuario_sem_permissao = usuario_factory("responde-revisao-sem-permissao")
    _, revisao_sem_permissao = _adicionar_revisao(
        db,
        usuario,
        usuario_sem_permissao,
        pergunta="Quais documentos são necessários para compra e venda?",
        resposta="Resposta sem autoria administrativa sobre compra e venda.",
    )

    fontes = buscar_respostas_revisadas_admin(
        db, "Quais documentos são necessários para compra e venda?"
    )

    assert [item["fonte_id"] for item in fontes] == [f"FONTE-{respondida.id}"]
    assert "CPF" not in fontes[0]["conteudo"]
    assert str(resposta_com_dado_pessoal.id) not in fontes[0]["fonte_id"]
    assert str(revisao_sem_permissao.id) not in fontes[0]["fonte_id"]


def test_consulta_prefere_entendimento_publicado_e_persiste_snapshot(
    client,
    db,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("consulta-entendimento-prioritario")
    admin = usuario_factory("admin-entendimento-prioritario", role="ADMIN")
    documento, chunk = _adicionar_entendimento(
        db,
        admin,
        titulo="Checklist administrativo de Compra e Venda",
        conteudo=(
            "Na compra e venda, o vendedor apresenta matrícula atualizada e "
            "comprova a titularidade do imóvel."
        ),
    )
    chunks_adicionais = []
    for posicao, conteudo in enumerate(
        (
            "Documentos do vendedor: certidão de estado civil atualizada e documento pessoal.",
            "Documentos do comprador: identificação pessoal e comprovantes indicados no checklist.",
        ),
        start=2,
    ):
        adicional = DocumentoChunk(
            documento_id=documento.id,
            pagina=1,
            posicao=posicao,
            conteudo=conteudo,
        )
        db.add(adicional)
        chunks_adicionais.append(conteudo)
    db.commit()
    chamada_modelo = []

    def responder(*, pergunta, contexto, historico):
        chamada_modelo.append(contexto)
        for conteudo in chunks_adicionais:
            assert conteudo in contexto
        return (
            "Na compra e venda, o vendedor apresenta a matrícula atualizada "
            "para conferir a titularidade do imóvel. [FONTE-1]"
        )

    def busca_documental_nao_esperada(*args, **kwargs):
        raise AssertionError(
            "Uma resposta administrativa suficiente deve ter prioridade."
        )

    monkeypatch.setattr(consultation_router, "gerar_resposta", responder)
    monkeypatch.setattr(
        consultation_router, "buscar_chunks_semelhantes", busca_documental_nao_esperada
    )

    resposta = client.post(
        "/api/consultar",
        headers=auth_headers(usuario),
        json={"consulta": "Na compra e venda, como verifico a titularidade do imóvel?"},
    )

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["situacao_resposta"] == "EVIDENCIA_SUFFICIENTE"
    assert dados["resultados"][0]["documento"] == documento.titulo
    assert documento.titulo in chamada_modelo[0]
    assert len(dados["resultados"]) == 1
    assert (
        db.query(ConsultaFonte).filter_by(consulta_id=uuid.UUID(dados["id"])).count()
        == 3
    )
    fonte_salva = (
        db.query(ConsultaFonte)
        .filter_by(consulta_id=uuid.UUID(dados["id"]), chunk_id=chunk.id)
        .one()
    )
    assert fonte_salva.documento_id == documento.id
    assert fonte_salva.chunk_id == chunk.id
    assert fonte_salva.citada is True


def test_consulta_usa_resposta_revisada_antes_dos_documentos_e_registra_snapshot(
    client,
    db,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("consulta-revisao-prioritaria")
    admin = usuario_factory("admin-revisao-prioritaria", role="ADMIN")
    _adicionar_revisao(
        db,
        usuario,
        admin,
        pergunta="Quais documentos são necessários para compra e venda?",
        resposta=(
            "Na compra e venda, confira a matrícula atualizada e a prova de "
            "titularidade do imóvel."
        ),
    )
    contextos = []

    def responder(*, pergunta, contexto, historico):
        contextos.append(contexto)
        return (
            "Na compra e venda, a matrícula atualizada e a prova de titularidade "
            "do imóvel devem ser conferidas. [FONTE-1]"
        )

    def busca_documental_nao_esperada(*args, **kwargs):
        raise AssertionError(
            "A revisão humana correspondente deve ser consultada antes."
        )

    monkeypatch.setattr(consultation_router, "gerar_resposta", responder)
    monkeypatch.setattr(
        consultation_router, "buscar_chunks_semelhantes", busca_documental_nao_esperada
    )

    resposta = client.post(
        "/api/consultar",
        headers=auth_headers(usuario),
        json={"consulta": "Quais documentos são necessários para compra e venda?"},
    )

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["situacao_resposta"] == "EVIDENCIA_SUFFICIENTE"
    assert dados["resultados"][0]["documento"] == "Resposta revisada pelo ADMIN"
    assert "Natureza da fonte: Resposta humana revisada pelo ADMIN" in contextos[0]
    fonte_salva = (
        db.query(ConsultaFonte).filter_by(consulta_id=uuid.UUID(dados["id"])).one()
    )
    assert fonte_salva.documento_id is None
    assert fonte_salva.chunk_id is None
    assert fonte_salva.trecho == (
        "Na compra e venda, confira a matrícula atualizada e a prova de "
        "titularidade do imóvel."
    )


def test_consulta_recupera_documentos_quando_nao_ha_conhecimento_humano(
    client,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("consulta-fallback-documentos")
    fonte = {
        "fonte_id": "FONTE-55555555-5555-5555-5555-555555555555",
        "chunk_id": "55555555-5555-5555-5555-555555555555",
        "documento_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "documento": "Norma fictícia — teste local",
        "versao_documento": None,
        "pagina": 3,
        "localizacao": "Página 3",
        "posicao": 1,
        "artigo": None,
        "capitulo": None,
        "secao": None,
        "paragrafo": None,
        "inciso": None,
        "conteudo": (
            "Na compra e venda, o vendedor comprova a titularidade do imóvel "
            "com a matrícula atualizada."
        ),
        "similaridade": 0.9,
    }
    buscas = []
    monkeypatch.setattr(
        consultation_router,
        "buscar_chunks_semelhantes",
        lambda _db, consulta, limite: buscas.append(consulta) or [fonte],
    )
    monkeypatch.setattr(
        consultation_router,
        "gerar_resposta",
        lambda **_: (
            "Na compra e venda, o vendedor comprova a titularidade do imóvel "
            "com a matrícula atualizada. [FONTE-1]"
        ),
    )

    resposta = client.post(
        "/api/consultar",
        headers=auth_headers(usuario),
        json={"consulta": "Como confiro a titularidade do vendedor na compra e venda?"},
    )

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["situacao_resposta"] == "EVIDENCIA_SUFFICIENTE"
    assert dados["resultados"][0]["documento"] == fonte["documento"]
    assert buscas


def test_documentos_complementam_entendimento_humano_parcial(
    client,
    db,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("consulta-complemento-documental")
    admin = usuario_factory("admin-complemento-documental", role="ADMIN")
    _adicionar_entendimento(
        db,
        admin,
        titulo="Checklist de Compra e Venda",
        conteudo=(
            "Na compra e venda, o vendedor deve comprovar a titularidade do imóvel "
            "pela matrícula atualizada."
        ),
    )
    documento = {
        "fonte_id": "FONTE-66666666-6666-6666-6666-666666666666",
        "chunk_id": "66666666-6666-6666-6666-666666666666",
        "documento_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "documento": "Norma fictícia sobre tributos — teste local",
        "versao_documento": None,
        "pagina": 4,
        "localizacao": "Página 4",
        "posicao": 1,
        "artigo": None,
        "capitulo": None,
        "secao": None,
        "paragrafo": None,
        "inciso": None,
        "conteudo": (
            "Na compra e venda, deve ser apresentada a certidão de quitação do IPTU."
        ),
        "similaridade": 0.88,
    }
    contextos = []

    def responder(*, pergunta, contexto, historico):
        contextos.append(contexto)
        if len(contextos) == 1:
            return (
                "A matrícula atualizada comprova a titularidade do vendedor. "
                "A certidão de quitação do IPTU também deve ser apresentada. "
                "[FONTE-1]"
            )
        return (
            "A matrícula atualizada comprova a titularidade do vendedor. "
            "[FONTE-1] A certidão de quitação do IPTU deve ser apresentada. "
            "[FONTE-2]"
        )

    monkeypatch.setattr(
        consultation_router,
        "buscar_chunks_semelhantes",
        lambda *_args, **_kwargs: [documento],
    )
    monkeypatch.setattr(consultation_router, "gerar_resposta", responder)

    resposta = client.post(
        "/api/consultar",
        headers=auth_headers(usuario),
        json={
            "consulta": (
                "Na compra e venda, o vendedor deve comprovar a matrícula atualizada "
                "e apresentar certidão de quitação do IPTU?"
            )
        },
    )

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["situacao_resposta"] == "EVIDENCIA_SUFFICIENTE"
    assert len(contextos) == 2
    assert "Checklist de Compra e Venda" in contextos[0]
    assert "Norma fictícia sobre tributos" in contextos[1]
    assert {fonte["documento"] for fonte in dados["resultados"]} == {
        "Checklist de Compra e Venda",
        "Norma fictícia sobre tributos — teste local",
    }
