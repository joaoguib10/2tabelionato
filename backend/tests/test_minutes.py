import json

from app.models import Documento, DocumentoPagina
from app.routers import minutes as minutes_router
from app.services.minute_service import completar_dados_certidao


def criar_modelo(db, usuario, tipo_ato="COMPRA_VENDA", titulo="Modelo oficial"):
    modelo = Documento(
        titulo=titulo,
        tipo="MODELO_MINUTA",
        tipo_ato=tipo_ato,
        situacao="APROVADO",
        nome_arquivo="modelo.txt",
        caminho_arquivo="arquivo-de-teste",
        criado_por=usuario.id,
        ativo=True,
        status="PRONTO",
        situacao_extracao="PROCESSADO_COMPLETO",
        status_seguranca="LIBERADO",
        versao="1.0",
        orgao_origem="Tabelionato de teste",
    )
    db.add(modelo)
    db.flush()
    db.add(
        DocumentoPagina(
            documento_id=modelo.id,
            pagina=1,
            pagina_confiavel=False,
            localizacao="Documento sem paginação física",
            conteudo="ESTRUTURA APROVADA DA MINUTA",
        )
    )
    db.commit()
    db.refresh(modelo)
    return modelo


def test_minuta_aceita_jpeg_sem_persistir_anexo(
    client,
    db,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("minutador", role="ADMIN")
    modelo = criar_modelo(db, usuario)
    analisados = []
    geracao = {}
    monkeypatch.setattr(
        minutes_router,
        "analisar_arquivo",
        lambda nome, conteudo, finalidade: analisados.append(
            (nome, conteudo, finalidade)
        )
        or "Certidão emitida em 01/09/2026, sem averbações.",
    )
    monkeypatch.setattr(minutes_router, "estruturar_analise", lambda *args: {})
    monkeypatch.setattr(
        minutes_router,
        "gerar_minuta",
        lambda tipo, dados, documentos, modelo_texto: geracao.update(
            {"tipo": tipo, "modelo": modelo_texto}
        )
        or "MINUTA PARA CONFERÊNCIA",
    )

    resposta = client.post(
        "/api/minutas/gerar",
        headers=auth_headers(usuario),
        data={
            "tipo_ato": "COMPRA_VENDA",
            "modelo_id": str(modelo.id),
            "dados_json": json.dumps({"alienantes": [{"nome": "Ana"}]}),
            "confirmado": "true",
        },
        files=[
            (
                "certidoes_alienantes",
                ("certidao.jpeg", b"\xff\xd8\xffdados-da-foto", "image/jpeg"),
            )
        ],
    )

    assert resposta.status_code == 200
    assert resposta.json()["minuta"] == "MINUTA PARA CONFERÊNCIA"
    assert resposta.json()["modelo_utilizado"]["id"] == str(modelo.id)
    assert analisados[0][0] == "certidao.jpeg"
    assert geracao["modelo"] == "ESTRUTURA APROVADA DA MINUTA"
    assert db.query(Documento).count() == 1


def test_minuta_rejeita_arquivo_disfarcado(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    usuario = usuario_factory("minutador2", role="ADMIN")
    modelo = criar_modelo(db, usuario, "DOACAO")
    resposta = client.post(
        "/api/minutas/gerar",
        headers=auth_headers(usuario),
        data={
            "tipo_ato": "DOACAO",
            "modelo_id": str(modelo.id),
            "dados_json": "{}",
            "confirmado": "true",
        },
        files=[
            (
                "matriculas",
                ("matricula.jpg", b"isto-nao-e-uma-imagem", "image/jpeg"),
            )
        ],
    )
    assert resposta.status_code == 400


def test_modelos_sao_filtrados_por_tipo_e_governanca(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    usuario = usuario_factory("modelos", role="ADMIN")
    compra = criar_modelo(db, usuario, "COMPRA_VENDA", "Compra")
    criar_modelo(db, usuario, "DOACAO", "Doação")
    rascunho = criar_modelo(db, usuario, "COMPRA_VENDA", "Rascunho")
    rascunho.situacao = "RASCUNHO"
    db.commit()

    resposta = client.get(
        "/api/minutas/modelos?tipo_ato=COMPRA_VENDA",
        headers=auth_headers(usuario),
    )
    assert resposta.status_code == 200
    assert [item["id"] for item in resposta.json()] == [str(compra.id)]


def test_minuta_rejeita_modelo_de_outro_tipo(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    usuario = usuario_factory("modelo-incorreto", role="ADMIN")
    modelo = criar_modelo(db, usuario, "DOACAO")
    resposta = client.post(
        "/api/minutas/gerar",
        headers=auth_headers(usuario),
        data={
            "tipo_ato": "COMPRA_VENDA",
            "modelo_id": str(modelo.id),
            "dados_json": "{}",
            "confirmado": "true",
        },
    )
    assert resposta.status_code == 422


def test_minuta_rejeita_modelo_acima_do_limite(
    client,
    db,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("modelo-longo", role="ADMIN")
    modelo = criar_modelo(db, usuario)
    monkeypatch.setattr(minutes_router, "MINUTA_MODEL_CONTEXT_LIMIT", 10)

    resposta = client.post(
        "/api/minutas/gerar",
        headers=auth_headers(usuario),
        data={
            "tipo_ato": "COMPRA_VENDA",
            "modelo_id": str(modelo.id),
            "dados_json": "{}",
            "confirmado": "true",
        },
    )
    assert resposta.status_code == 413
    assert "modelo aprovado excede" in resposta.json()["detail"].lower()


def test_minuta_rejeita_contexto_total_acima_do_limite(
    client,
    db,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("contexto-longo", role="ADMIN")
    modelo = criar_modelo(db, usuario)
    monkeypatch.setattr(minutes_router, "MINUTA_TOTAL_CONTEXT_LIMIT", 35)

    resposta = client.post(
        "/api/minutas/gerar",
        headers=auth_headers(usuario),
        data={
            "tipo_ato": "COMPRA_VENDA",
            "modelo_id": str(modelo.id),
            "dados_json": json.dumps({"observacoes": "texto adicional"}),
            "confirmado": "true",
        },
    )
    assert resposta.status_code == 413
    assert "conjunto de modelo" in resposta.json()["detail"].lower()


def test_certidao_normaliza_partes_e_calcula_validade_do_alienante():
    resultado = completar_dados_certidao(
        {
            "nomes": ["Parte Um", "Parte Dois"],
            "cpfs": ["00000000000", "11111111111"],
            "data_emissao": "01/09/2026",
            "regime_bens": "comunhão parcial",
            "data_casamento": "10/08/2020",
            "data_registro_casamento": "12/08/2020",
        },
        "certidão do vendedor/doador",
    )

    assert resultado["pessoas"][0] == {
        "nome": "Parte Um",
        "cpf": "00000000000",
    }
    assert resultado["data_emissao"] == "2026-09-01"
    assert resultado["data_validade"] == "2026-11-30"
    assert resultado["data_casamento"] == "2020-08-10"
    assert resultado["data_registro_casamento"] == "2020-08-12"


def test_certidao_do_adquirente_nao_inventa_validade():
    resultado = completar_dados_certidao(
        {"pessoas": [{"nome": "Parte"}], "data_emissao": "2026-09-01"},
        "certidão do comprador/donatário",
    )
    assert "data_validade" not in resultado
