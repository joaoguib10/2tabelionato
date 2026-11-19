from types import SimpleNamespace

import pytest
from app.models import (
    ConsultaHistorico,
    ConsultaRevisao,
    Documento,
    DocumentoChunk,
    IAExternaFonte,
    utc_now,
)
from app.routers import consultation as consultation_router
from app.services.consultation_knowledge_service import (
    _filtro_candidatos_entendimento,
    _referencias_artigo,
    buscar_entendimentos_publicados,
    buscar_documentos_institucionais_publicos,
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
    assert " || " in str(consulta)
    assert "dissolucao" in consulta.params.values()


def test_busca_institucional_inclui_entendimento_especifico_junto_das_normas(
    db, usuario_factory
):
    admin = usuario_factory("admin-busca-inventario", role="ADMIN")
    norma = Documento(
        titulo="Código de Normas",
        tipo="NORMA",
        situacao="APROVADO",
        liberacao_externa="PUBLICO",
        ativo=True,
        status="PRONTO",
        status_seguranca="LIBERADO",
        situacao_extracao="PROCESSADO_COMPLETO",
        nome_arquivo="codigo-normas.txt",
        caminho_arquivo="nao-utilizado",
        criado_por=admin.id,
    )
    entendimento = Documento(
        titulo="Documentos - Inventário",
        tipo="ENTENDIMENTO",
        situacao="APROVADO",
        liberacao_externa="PUBLICO",
        ativo=True,
        status="PRONTO",
        status_seguranca="LIBERADO",
        situacao_extracao="PROCESSADO_COMPLETO",
        nome_arquivo="documentos-inventario.txt",
        caminho_arquivo="nao-utilizado",
        criado_por=admin.id,
    )
    db.add_all([norma, entendimento])
    db.flush()

    texto_norma = (
        "No inventário extrajudicial, a escritura pública deve observar a norma. "
        * 10
    )
    chunks_norma = [
        DocumentoChunk(
            documento_id=norma.id,
            pagina=1,
            posicao=posicao,
            conteudo=texto_norma,
        )
        for posicao in range(1, 11)
    ]
    chunk_entendimento = DocumentoChunk(
        documento_id=entendimento.id,
        pagina=1,
        posicao=1,
        conteudo=(
            "Documentos para inventário extrajudicial: conferir herdeiros, "
            "partilha e os documentos necessários à escritura pública."
        ),
    )
    db.add_all([*chunks_norma, chunk_entendimento])
    db.flush()

    fontes = [
        IAExternaFonte(
            escopo="INSTITUCIONAL",
            tipo_fonte="DOCUMENTO",
            fonte_local_id=str(chunk.id),
            documento_id=documento.id,
            tier="DOCUMENTOS" if documento.tipo == "NORMA" else "ENTENDIMENTO",
            pagina=1,
            versao_hash=f"hash-{chunk.id}",
            classificacao="PUBLICO",
            nome_remoto=f"teste-{chunk.id}",
            status="INDEXADO",
        )
        for documento, chunk in [
            (norma, chunks_norma[0]),
            (entendimento, chunk_entendimento),
        ]
    ]
    db.add_all(fontes)
    db.commit()

    resultados = buscar_documentos_institucionais_publicos(
        db,
        "Quais documentos são necessários para escritura pública de inventário extrajudicial?",
        limite=8,
    )

    documentos_encontrados = [item["documento"] for item in resultados]
    assert documentos_encontrados[0] == "Documentos - Inventário"
    assert "Código de Normas" in documentos_encontrados


def test_busca_doacao_expande_anuencia_para_dispositivos_sobre_descendentes(
    db, usuario_factory
):
    admin = usuario_factory("admin-busca-doacao", role="ADMIN")
    checklist = Documento(
        titulo="Documentos - Doação",
        tipo="ENTENDIMENTO",
        situacao="APROVADO",
        liberacao_externa="PUBLICO",
        ativo=True,
        status="PRONTO",
        status_seguranca="LIBERADO",
        situacao_extracao="PROCESSADO_COMPLETO",
        nome_arquivo="documentos-doacao.txt",
        caminho_arquivo="nao-utilizado",
        criado_por=admin.id,
    )
    codigo_civil = Documento(
        titulo="Código Civil",
        tipo="LEGISLACAO",
        situacao="APROVADO",
        liberacao_externa="PUBLICO",
        ativo=True,
        status="PRONTO",
        status_seguranca="LIBERADO",
        situacao_extracao="PROCESSADO_COMPLETO",
        nome_arquivo="codigo-civil.txt",
        caminho_arquivo="nao-utilizado",
        criado_por=admin.id,
    )
    db.add_all([checklist, codigo_civil])
    db.flush()

    chunks_checklist = [
        DocumentoChunk(
            documento_id=checklist.id,
            pagina=1,
            posicao=posicao,
            conteudo=(
                "Na doação, conferir a qualificação do doador e do donatário, "
                "documentos pessoais e dados do imóvel."
            ),
        )
        for posicao in range(1, 9)
    ]
    chunks_legais = [
        DocumentoChunk(
            documento_id=codigo_civil.id,
            pagina=205,
            posicao=1,
            artigo="Art. 544",
            artigo_confirmado=True,
            conteudo=(
                "Art. 544. A doação de ascendentes a descendentes, ou de um cônjuge "
                "a outro, importa adiantamento do que lhes cabe por herança."
            ),
        ),
        DocumentoChunk(
            documento_id=codigo_civil.id,
            pagina=199,
            posicao=1,
            artigo="Art. 496",
            artigo_confirmado=True,
            conteudo=(
                "Art. 496. É anulável a venda de ascendente a descendente, salvo "
                "se os outros descendentes e o cônjuge do alienante consentirem."
            ),
        ),
    ]
    db.add_all([*chunks_checklist, *chunks_legais])
    db.flush()
    db.add_all(
        [
            IAExternaFonte(
                escopo="INSTITUCIONAL",
                tipo_fonte="DOCUMENTO",
                fonte_local_id=str(chunk.id),
                documento_id=documento.id,
                tier=(
                    "ENTENDIMENTO"
                    if documento.tipo == "ENTENDIMENTO"
                    else "DOCUMENTOS"
                ),
                pagina=chunk.pagina,
                versao_hash=f"hash-{documento.id}-{chunk.pagina}",
                classificacao="PUBLICO",
                nome_remoto=f"doacao-{documento.id}-{chunk.pagina}",
                status="INDEXADO",
            )
            for documento, chunk in [
                (checklist, chunks_checklist[0]),
                *((codigo_civil, chunk) for chunk in chunks_legais),
            ]
        ]
    )
    db.commit()

    resultados = buscar_documentos_institucionais_publicos(
        db,
        "Em uma doação, é necessária a anuência dos demais filhos do doador?",
        limite=8,
    )

    assert any("adiantamento" in item["conteudo"] for item in resultados)
    assert any(item.get("artigo") == "Art. 544" for item in resultados)
    assert any(item.get("artigo") == "Art. 496" for item in resultados)


def test_busca_artigo_explicito_normaliza_numeracao_e_respeita_documento_citado(
    db, usuario_factory
):
    admin = usuario_factory("admin-busca-artigo-exato", role="ADMIN")
    codigo_civil = Documento(
        titulo="Código Civil",
        tipo="LEGISLACAO",
        situacao="APROVADO",
        liberacao_externa="PUBLICO",
        ativo=True,
        status="PRONTO",
        status_seguranca="LIBERADO",
        situacao_extracao="PROCESSADO_COMPLETO",
        nome_arquivo="codigo-civil.pdf",
        caminho_arquivo="nao-utilizado",
        criado_por=admin.id,
    )
    codigo_normas = Documento(
        titulo="Código de Normas",
        tipo="NORMA",
        situacao="APROVADO",
        liberacao_externa="PUBLICO",
        ativo=True,
        status="PRONTO",
        status_seguranca="LIBERADO",
        situacao_extracao="PROCESSADO_COMPLETO",
        nome_arquivo="codigo-normas.pdf",
        caminho_arquivo="nao-utilizado",
        criado_por=admin.id,
    )
    db.add_all([codigo_civil, codigo_normas])
    db.flush()
    chunks = [
        DocumentoChunk(
            documento_id=codigo_civil.id,
            pagina=353,
            posicao=1,
            artigo="Art. 1.647",
            artigo_confirmado=True,
            conteudo="Art. 1.647. Regra sintética do Código Civil.",
        ),
        DocumentoChunk(
            documento_id=codigo_normas.id,
            pagina=149,
            posicao=1,
            artigo="Art. 500",
            artigo_confirmado=True,
            conteudo="Art. 500. Regra sintética do Código de Normas.",
        ),
    ]
    db.add_all(chunks)
    db.flush()
    for documento, chunk in zip((codigo_civil, codigo_normas), chunks):
        db.add(
            IAExternaFonte(
                escopo="INSTITUCIONAL",
                tipo_fonte="DOCUMENTO",
                fonte_local_id=str(chunk.id),
                documento_id=documento.id,
                tier="DOCUMENTOS",
                pagina=chunk.pagina,
                versao_hash=f"hash-{documento.id}",
                classificacao="PUBLICO",
                nome_remoto=f"artigos-{documento.id}",
                status="INDEXADO",
            )
        )
    db.commit()

    assert _referencias_artigo("O que diz o artigo 1647 do Código Civil?") == [
        "1647"
    ]
    assert _referencias_artigo("O que diz o artigo 500 do Código de Normas?") == [
        "500"
    ]
    resultado_civil = buscar_documentos_institucionais_publicos(
        db, "O que diz o artigo 1647 do Código Civil?", limite=8
    )
    resultado_normas = buscar_documentos_institucionais_publicos(
        db, "O que diz o artigo 500 do Código de Normas?", limite=8
    )

    assert [fonte["documento"] for fonte in resultado_civil] == ["Código Civil"]
    assert resultado_civil[0]["artigo"] == "Art. 1.647"
    assert [fonte["documento"] for fonte in resultado_normas] == [
        "Código de Normas"
    ]
    assert resultado_normas[0]["artigo"] == "Art. 500"


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
