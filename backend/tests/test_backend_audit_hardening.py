import uuid

import pytest
from app.models import ConsultaHistorico, ConsultaRevisao, Documento, DocumentoChunk
from app.prompts import BASE_PROMPT_VERSION, CONSULTA_PROMPT_VERSION
from app.schemas import RevisaoRespostaRequest
from app.services.chunk_service import extrair_artigo
from app.services.ollama_service import (
    CONSULTA_PROMPT_AUDIT_VERSION,
    obter_metadados_consulta,
)
from app.services.semantic_search_service import (
    _buscar_chunks_por_artigos,
    extrair_referencias_artigos,
)
from pydantic import ValidationError


def _documento_juridico(db, usuario, titulo: str, tipo: str = "NORMA") -> Documento:
    documento = Documento(
        titulo=titulo,
        tipo=tipo,
        situacao="APROVADO" if tipo == "NORMA" else "RASCUNHO",
        nome_arquivo=f"{uuid.uuid4()}.txt",
        caminho_arquivo=f"privado-{uuid.uuid4()}",
        criado_por=usuario.id,
        ativo=True,
        status="PRONTO",
        situacao_extracao="PROCESSADO_COMPLETO",
        status_seguranca="LIBERADO",
    )
    db.add(documento)
    db.flush()
    return documento


def test_entendimento_de_revisao_nao_pode_ser_recategorizado(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    autor = usuario_factory("autor-governanca-revisao")
    admin = usuario_factory("admin-governanca-revisao", role="USUARIO")
    master = usuario_factory("master-governanca-revisao", role="ADMIN")
    consulta = ConsultaHistorico(
        usuario_id=autor.id,
        pergunta="Pergunta genérica para revisão?",
        resposta="Resposta original.",
        situacao_resposta="EVIDENCIA_PARCIAL",
        fonte_ids="[]",
    )
    db.add(consulta)
    db.flush()
    entendimento = _documento_juridico(
        db,
        master,
        "Entendimento interno controlado",
        tipo="ENTENDIMENTO",
    )
    db.add(
        ConsultaRevisao(
            consulta_id=consulta.id,
            status="RESPONDIDA",
            resposta_humana="Orientação humana genérica.",
            entendimento_documento_id=entendimento.id,
        )
    )
    db.commit()

    for usuario in (admin, master):
        resposta = client.patch(
            f"/api/documentos/{entendimento.id}",
            headers=auth_headers(usuario),
            json={"tipo": "NORMA"},
        )
        assert resposta.status_code == (409 if usuario.role == "ADMIN" else 403)

    db.refresh(entendimento)
    assert entendimento.tipo == "ENTENDIMENTO"


def test_admin_nao_recategoriza_entendimento_mesmo_sem_vinculo_ativo(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    admin = usuario_factory("admin-sem-bypass-entendimento", role="USUARIO")
    master = usuario_factory("master-entendimento-avulso", role="ADMIN")
    entendimento = _documento_juridico(
        db,
        master,
        "Entendimento avulso controlado",
        tipo="ENTENDIMENTO",
    )
    db.commit()

    resposta = client.patch(
        f"/api/documentos/{entendimento.id}",
        headers=auth_headers(admin),
        json={"tipo": "NORMA"},
    )

    assert resposta.status_code == 403
    db.refresh(entendimento)
    assert entendimento.tipo == "ENTENDIMENTO"


def test_extrai_artigos_ordinais_compostos_e_listas():
    referencias = extrair_referencias_artigos(
        "Compare os arts. 10, 11 e 12 com o Art. 1º e o Art. 1.198-A."
    )

    assert referencias == [
        "Art. 10",
        "Art. 11",
        "Art. 12",
        "Art. 1º",
        "Art. 1.198-A",
    ]


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Art. 1º Esta é a regra inicial.", "Art. 1º"),
        ("Art. 1.198-A. Esta é a regra especial.", "Art. 1.198-A"),
        ("Artigo 11 Regra escrita por extenso.", "Art. 11"),
    ],
)
def test_chunk_preserva_numero_juridico_do_artigo(texto, esperado):
    assert extrair_artigo(texto) == esperado


def test_pista_do_titulo_prioriza_sem_ocultar_artigo_homonimo(
    db,
    usuario_factory,
):
    usuario = usuario_factory("titulo-artigo")
    documento_generico = _documento_juridico(db, usuario, "A Norma Genérica")
    documento_indicado = _documento_juridico(db, usuario, "Z Código Especial")
    for documento in (documento_generico, documento_indicado):
        db.add(
            DocumentoChunk(
                documento_id=documento.id,
                pagina=1,
                posicao=1,
                artigo="Art. 10",
                artigo_confirmado=True,
                pagina_confiavel=True,
                conteudo=f"Art. 10 Regra de {documento.titulo}.",
            )
        )
    db.commit()

    resultados = _buscar_chunks_por_artigos(
        db,
        ["Art. 10"],
        limite=2,
        consulta="No Z Código Especial, o que determina o Art. 10?",
    )

    assert [item["documento"] for item in resultados] == [
        "Z Código Especial",
        "A Norma Genérica",
    ]


@pytest.mark.parametrize(
    ("artigo_armazenado", "artigo_consultado"),
    [
        ("Art. 1º", "Art. 1"),
        ("Art. 1.198-A", "Art. 1.198-A"),
    ],
)
def test_busca_direta_normaliza_formatos_do_numero_do_artigo(
    db,
    usuario_factory,
    artigo_armazenado,
    artigo_consultado,
):
    usuario = usuario_factory(f"artigo-{uuid.uuid4().hex[:8]}")
    documento = _documento_juridico(db, usuario, "Código de teste")
    db.add(
        DocumentoChunk(
            documento_id=documento.id,
            pagina=1,
            posicao=1,
            artigo=artigo_armazenado,
            artigo_confirmado=True,
            pagina_confiavel=True,
            conteudo=f"{artigo_armazenado} Regra controlada.",
        )
    )
    db.commit()

    resultados = _buscar_chunks_por_artigos(
        db,
        [artigo_consultado],
        limite=1,
        consulta=f"Explique o {artigo_consultado} do Código de teste.",
    )

    assert len(resultados) == 1
    assert resultados[0]["artigo"] == artigo_armazenado


def test_resposta_humana_rejeita_apenas_espacos_e_normaliza_texto():
    with pytest.raises(ValidationError):
        RevisaoRespostaRequest(resposta_humana="   ")

    dados = RevisaoRespostaRequest(resposta_humana="  Resposta válida.  ")
    assert dados.resposta_humana == "Resposta válida."


def test_versao_auditada_da_consulta_inclui_prompt_base():
    assert CONSULTA_PROMPT_VERSION in CONSULTA_PROMPT_AUDIT_VERSION
    assert BASE_PROMPT_VERSION in CONSULTA_PROMPT_AUDIT_VERSION
    assert obter_metadados_consulta()["prompt_version"] == CONSULTA_PROMPT_AUDIT_VERSION
