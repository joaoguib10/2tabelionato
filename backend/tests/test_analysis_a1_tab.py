from app.models import Caso, CasoAnalise, CasoDecisao, CasoFato, CasoVersao
from app.services import case_legal_analysis_service as a1


def _caso_pronto(db, usuario):
    caso = Caso(
        titulo="Compra e venda sintética",
        tipo_ato="COMPRA E VENDA",
        status="PRONTO_PARA_ANALISE",
        criado_por=usuario.id,
        responsavel_id=usuario.id,
    )
    db.add(caso)
    db.flush()
    db.add(
        CasoFato(
            caso_id=caso.id,
            campo="valor do negócio",
            valor_original="1000",
            valor_atual="1000",
            proveniencia="DECLARADA",
            estado_evidencia="ENCONTRADO",
            estado_conferencia="CONFIRMADO",
        )
    )
    db.commit()
    return caso


def test_a1_preserva_versao_fontes_e_nao_decide(
    client,
    db,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("responsavel-a1")
    caso = _caso_pronto(db, usuario)
    fonte = {
        "fonte_id": "FONTE-11111111-1111-1111-1111-111111111111",
        "chunk_id": "11111111-1111-1111-1111-111111111111",
        "documento_id": "22222222-2222-2222-2222-222222222222",
        "documento": "Norma sintética",
        "versao_documento": "1",
        "pagina": 2,
        "localizacao": "Página 2",
        "artigo": "Art. 1",
        "conteudo": "Regra sintética aplicável ao caso.",
        "similaridade": 0.8,
    }
    monkeypatch.setattr(
        a1, "buscar_chunks_semelhantes", lambda *args, **kwargs: [fonte]
    )
    monkeypatch.setattr(
        a1,
        "_gerar_analise",
        lambda _: {
            "resumo": "Há regra a conferir.",
            "requisitos": ["Conferir requisito sintético"],
            "impedimentos": [],
            "pendencias": [],
            "fonte_ids": [fonte["fonte_id"], "FONTE-inventada"],
        },
    )
    resposta = client.post(
        f"/api/analises/casos/{caso.id}/analises-juridicas",
        headers=auth_headers(usuario),
    )
    assert resposta.status_code == 201
    dados = resposta.json()
    assert dados["versao_numero"] == 1
    assert dados["status_evidencia"] == "EVIDENCIA_PARCIAL"
    assert len(dados["fontes"]) == 1 and dados["fontes"][0]["citada"] is True
    assert db.query(CasoVersao).count() == 1
    assert db.query(CasoAnalise).count() == 1
    db.refresh(caso)
    assert caso.status == "ANALISE_DISPONIVEL"


def test_tab_e_decisao_exclusivamente_humana_do_admin(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    usuario = usuario_factory("responsavel-tab")
    admin = usuario_factory("admin-tab", role="ADMIN")
    caso = _caso_pronto(db, usuario)
    versao = a1.obter_ou_criar_versao(db, caso, usuario)
    analise = CasoAnalise(
        caso_id=caso.id,
        versao_id=versao.id,
        status_evidencia="BASE_INSUFICIENTE",
        resumo="Sem base suficiente.",
        requisitos=[],
        impedimentos=[],
        pendencias=[],
        fontes_snapshot=[],
        prompt_version="teste",
        gerado_por=usuario.id,
    )
    db.add(analise)
    caso.status = "ANALISE_DISPONIVEL"
    db.commit()
    corpo = {
        "analise_id": str(analise.id),
        "decisao": "EXIGENCIA",
        "texto": "Apresentar documento sintético para conferência.",
    }
    url = f"/api/analises/casos/{caso.id}/decisoes"
    assert (
        client.post(url, headers=auth_headers(usuario), json=corpo).status_code == 403
    )
    resposta = client.post(url, headers=auth_headers(admin), json=corpo)
    assert resposta.status_code == 201
    assert resposta.json()["decidido_por"] == str(admin.id)
    assert db.query(CasoDecisao).count() == 1
    db.refresh(caso)
    assert caso.status == "DECISAO_REGISTRADA"
