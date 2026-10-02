"""Cenário sintético completo do estado factual até a decisão humana."""

from app.services import case_legal_analysis_service as a1


def test_fluxo_a2_a1_tab_preserva_conferencia_fontes_e_decisao_humana(
    client,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("responsavel-fluxo-completo")
    admin = usuario_factory("admin-fluxo-completo", role="ADMIN")
    headers_usuario = auth_headers(usuario)

    resposta = client.post(
        "/api/analises/casos",
        headers=headers_usuario,
        json={
            "titulo": "Compra e venda sintética ponta a ponta",
            "identificacao": "TESTE-E2E-001",
            "tipo_ato": "COMPRA_VENDA",
        },
    )
    assert resposta.status_code == 201
    caso_id = resposta.json()["id"]

    resposta = client.post(
        f"/api/analises/casos/{caso_id}/fatos",
        headers=headers_usuario,
        json={
            "campo": "valor do negócio",
            "categoria": "econômico",
            "locus": "E",
            "valor": "R$ 300.000,00",
            "proveniencia": "DECLARADA",
            "estado_evidencia": "ENCONTRADO",
        },
    )
    assert resposta.status_code == 201
    fato_id = resposta.json()["id"]
    assert resposta.json()["estado_conferencia"] == "PENDENTE"

    resposta = client.post(
        f"/api/analises/casos/{caso_id}/analises-juridicas",
        headers=headers_usuario,
    )
    assert resposta.status_code == 409

    resposta = client.post(
        f"/api/analises/casos/{caso_id}/fatos/{fato_id}/conferencias",
        headers=headers_usuario,
        json={"acao": "CONFIRMAR"},
    )
    assert resposta.status_code == 200
    assert resposta.json()["estado_conferencia"] == "CONFIRMADO"

    resposta = client.patch(
        f"/api/analises/casos/{caso_id}/status",
        headers=headers_usuario,
        json={"status": "PRONTO_PARA_ANALISE"},
    )
    assert resposta.status_code == 200

    fonte = {
        "fonte_id": "FONTE-11111111-1111-1111-1111-111111111111",
        "chunk_id": "11111111-1111-1111-1111-111111111111",
        "documento_id": "22222222-2222-2222-2222-222222222222",
        "documento": "Norma sintética de homologação",
        "versao_documento": "1",
        "pagina": 3,
        "localizacao": "Página 3",
        "artigo": "Art. 10",
        "conteudo": "Regra sintética aplicável ao negócio conferido.",
        "similaridade": 0.91,
    }
    monkeypatch.setattr(
        a1, "buscar_chunks_semelhantes", lambda *args, **kwargs: [fonte]
    )
    monkeypatch.setattr(
        a1,
        "_gerar_analise",
        lambda _: {
            "resumo": "O caso possui base documental para conferência humana.",
            "requisitos": ["Conferir a documentação original."],
            "impedimentos": [],
            "pendencias": [],
            "fonte_ids": [fonte["fonte_id"]],
        },
    )

    resposta = client.post(
        f"/api/analises/casos/{caso_id}/analises-juridicas",
        headers=headers_usuario,
    )
    assert resposta.status_code == 201
    analise = resposta.json()
    assert analise["status_evidencia"] == "EVIDENCIA_PARCIAL"
    assert analise["fontes"][0]["citada"] is True

    decisao = {
        "analise_id": analise["id"],
        "decisao": "APROVAR",
        "texto": "Decisão humana sintética registrada após conferência.",
        "fundamentacao": "Fundamentação sintética para teste.",
        "escopo": "Somente este caso sintético.",
    }
    url_decisao = f"/api/analises/casos/{caso_id}/decisoes"
    assert (
        client.post(url_decisao, headers=headers_usuario, json=decisao).status_code
        == 403
    )

    resposta = client.post(url_decisao, headers=auth_headers(admin), json=decisao)
    assert resposta.status_code == 201
    assert resposta.json()["decidido_por"] == str(admin.id)

    resposta = client.get(f"/api/analises/casos/{caso_id}", headers=headers_usuario)
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "DECISAO_REGISTRADA"
