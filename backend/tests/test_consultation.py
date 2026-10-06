from datetime import date, datetime

from app.models import Documento, DocumentoPagina
from app.routers import consultation as consultation_router
from app.services import ollama_service

FONTE_ID = "FONTE-11111111-1111-1111-1111-111111111111"


def test_limites_do_filtro_diario_respeitam_fuso_de_sao_paulo():
    dia = date(2026, 9, 4)

    assert consultation_router._limite_data_local_em_utc(
        dia, fim_do_dia=False
    ) == datetime(2026, 9, 4, 3, 0)
    assert consultation_router._limite_data_local_em_utc(
        dia, fim_do_dia=True
    ) == datetime(2026, 9, 5, 2, 59, 59, 999999)


def test_consulta_salva_fontes_e_feedback(
    client,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("consultor")
    monkeypatch.setattr(
        consultation_router,
        "buscar_chunks_semelhantes",
        lambda *args, **kwargs: [
            {
                "fonte_id": FONTE_ID,
                "chunk_id": "11111111-1111-1111-1111-111111111111",
                "documento_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "documento": "Manual",
                "versao_documento": "1.0",
                "pagina": 4,
                "localizacao": "Página 4",
                "posicao": 1,
                "artigo": "Art. 10",
                "capitulo": None,
                "secao": None,
                "paragrafo": None,
                "inciso": None,
                "conteudo": "A certidão vale 90 dias.",
                "similaridade": 0.82,
            }
        ],
    )
    monkeypatch.setattr(
        consultation_router,
        "gerar_resposta",
        lambda **kwargs: f"A certidão vale 90 dias. [{FONTE_ID}]",
    )

    resposta = client.post(
        "/api/consultar",
        headers=auth_headers(usuario),
        json={"consulta": "Qual a validade da certidão?", "historico": []},
    )
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["confiavel"] is True
    assert dados["situacao_resposta"] == "EVIDENCIA_SUFFICIENTE"
    assert dados["citacoes_verificadas"] == [FONTE_ID]
    assert FONTE_ID not in dados["resposta"]
    assert "Fundamentação: Manual, Art. 10." in dados["resposta"]

    feedback = client.patch(
        f"/api/consultar/{dados['id']}/feedback",
        headers=auth_headers(usuario),
        json={"produtiva": True},
    )
    assert feedback.status_code == 204

    historico = client.get(
        "/api/consultar/historico",
        headers=auth_headers(usuario),
    ).json()["items"]
    assert historico[0]["produtiva"] is True
    assert historico[0]["feedback_comentario"] is None
    assert historico[0]["usuario_nome"] == "Consultor"
    assert historico[0]["fonte_ids"] == [FONTE_ID]
    assert historico[0]["fontes"][0]["trecho"] == "A certidão vale 90 dias."
    assert historico[0]["fontes"][0]["citada"] is True
    assert historico[0]["tipo_tarefa"] == "CONSULTA"
    assert (
        historico[0]["prompt_version"] == ollama_service.CONSULTA_PROMPT_AUDIT_VERSION
    )
    assert historico[0]["modelo_ia"] == ollama_service.MODELO_GERACAO
    assert historico[0]["modelo_versao"] == (
        ollama_service.MODELO_GERACAO.rsplit(":", 1)[1]
        if ":" in ollama_service.MODELO_GERACAO
        else None
    )
    assert historico[0]["parametros_ia"] == {
        "temperature": 0.1,
        "num_ctx": 8192,
        "num_predict": ollama_service.OLLAMA_CONSULTA_MAX_TOKENS,
    }


def test_feedback_util_rejeita_motivo_ou_comentario(
    client,
    usuario_factory,
    auth_headers,
):
    usuario = usuario_factory("feedback-util-limpo")
    resposta = client.patch(
        "/api/consultar/11111111-1111-1111-1111-111111111111/feedback",
        headers=auth_headers(usuario),
        json={"produtiva": True, "comentario": "Não deve ser aceito."},
    )

    assert resposta.status_code == 422


def test_consulta_abaixo_do_limiar_nao_chama_modelo(
    client,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("semfonte")
    monkeypatch.setattr(
        consultation_router,
        "buscar_chunks_semelhantes",
        lambda *args, **kwargs: [],
    )
    resposta = client.post(
        "/api/consultar",
        headers=auth_headers(usuario),
        json={"consulta": "Pergunta sem respaldo"},
    )
    assert resposta.status_code == 200
    assert resposta.json()["confiavel"] is False
    assert resposta.json()["situacao_resposta"] == "BASE_INSUFICIENTE"
    assert resposta.json()["resultados"] == []


def test_consulta_associa_apenas_fonte_com_apoio_textual_quando_modelo_nao_cita(
    client,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("sem-citacao")
    fonte_nao_relacionada = {
        "fonte_id": "FONTE-22222222-2222-2222-2222-222222222222",
        "chunk_id": "22222222-2222-2222-2222-222222222222",
        "documento_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "documento": "Norma não relacionada",
        "versao_documento": None,
        "pagina": 2,
        "localizacao": "Página 2",
        "posicao": 2,
        "artigo": "Art. 2",
        "conteudo": "A certidão de nascimento será conferida no atendimento.",
        "similaridade": 0.99,
    }
    monkeypatch.setattr(
        consultation_router,
        "buscar_chunks_semelhantes",
        lambda *args, **kwargs: [
            {
                "fonte_id": FONTE_ID,
                "chunk_id": "11111111-1111-1111-1111-111111111111",
                "documento_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "documento": "Manual",
                "versao_documento": None,
                "pagina": 1,
                "localizacao": "Página 1",
                "posicao": 1,
                "artigo": "Art. 1",
                "conteudo": "A escritura exige conferência documental.",
                "similaridade": 0.8,
            },
            fonte_nao_relacionada,
        ],
    )
    monkeypatch.setattr(
        consultation_router,
        "gerar_resposta",
        lambda **kwargs: "A escritura exige conferência documental.",
    )
    resposta = client.post(
        "/api/consultar",
        headers=auth_headers(usuario),
        json={"consulta": "O que a escritura exige?"},
    )
    assert resposta.status_code == 200
    assert resposta.json()["citacoes_verificadas"] == [FONTE_ID]
    assert [item["documento"] for item in resposta.json()["resultados"]] == [
        "Manual"
    ]
    assert resposta.json()["situacao_resposta"] == "EVIDENCIA_SUFFICIENTE"
    assert "Fundamentação: Manual, Art. 1." in resposta.json()["resposta"]
    historico = client.get(
        "/api/consultar/historico",
        headers=auth_headers(usuario),
    ).json()["items"]
    assert historico[0]["fontes"][0]["citada"] is True
    assert historico[0]["fontes"][0]["recuperada"] is True
    assert historico[0]["fontes"][1]["citada"] is False


def test_consulta_descarta_raciocinio_em_ingles_e_nao_exibe_fontes(
    client,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("resposta-em-ingles")
    monkeypatch.setattr(
        consultation_router,
        "buscar_chunks_semelhantes",
        lambda *args, **kwargs: [
            {
                "fonte_id": FONTE_ID,
                "chunk_id": "11111111-1111-1111-1111-111111111111",
                "documento_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "documento": "Código de Normas",
                "versao_documento": None,
                "pagina": 315,
                "localizacao": "Capítulo V, Seção I",
                "posicao": 1,
                "artigo": "Art. 1.184",
                "conteudo": "Art. 1.184. A ata notarial pode registrar fatos e documentos.",
                "similaridade": 0.8,
            }
        ],
    )
    monkeypatch.setattr(
        consultation_router,
        "gerar_resposta",
        lambda **kwargs: (
            "Okay, let's tackle this query. The user provided legal excerpts. "
            "First, I need to understand what each excerpt is about. "
            f"[FONTE-{FONTE_ID.removeprefix('FONTE-')}]"
        ),
    )

    resposta = client.post(
        "/api/consultar",
        headers=auth_headers(usuario),
        json={"consulta": "Quais documentos são necessários para Ata Notarial?"},
    )

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["situacao_resposta"] == "EVIDENCIA_PARCIAL"
    assert dados["confiavel"] is False
    assert dados["citacoes_verificadas"] == [FONTE_ID]
    assert [item["documento"] for item in dados["resultados"]] == [
        "Código de Normas"
    ]
    assert "Não consegui confirmar um checklist completo" in dados["resposta"]
    assert "Art. 1.184" in dados["resposta"]
    assert "Okay" not in dados["resposta"]
    assert FONTE_ID not in dados["resposta"]


def test_resposta_final_em_portugues_e_direta_passa_pelo_filtro():
    assert consultation_router._resposta_direta_em_portugues(
        "Pode lavrar a ata quando os fatos forem comprovados. Não invente requisitos."
    )


def test_resposta_em_ingles_nao_passa_pelo_filtro():
    assert not consultation_router._resposta_direta_em_portugues(
        "The documents should be provided before the notarial deed is signed."
    )


def test_historico_recente_participa_da_recuperacao(
    client,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("continuidade")
    recebidas = []
    monkeypatch.setattr(
        consultation_router,
        "buscar_chunks_semelhantes",
        lambda db, consulta, limite: recebidas.append(consulta) or [],
    )
    resposta = client.post(
        "/api/consultar",
        headers=auth_headers(usuario),
        json={
            "consulta": "E quanto ao prazo?",
            "historico": [
                {
                    "papel": "usuario",
                    "conteudo": "Como funciona a certidão de casamento?",
                },
                {"papel": "assistente", "conteudo": "A regra depende da emissão."},
            ],
        },
    )
    assert resposta.status_code == 200
    assert "certidão de casamento" in recebidas[0]
    assert "E quanto ao prazo?" in recebidas[0]
    assert "A regra depende da emissão." not in recebidas[0]


def test_pergunta_autossuficiente_nao_herda_assunto_anterior():
    dados = consultation_router.ConsultaRequest(
        consulta="O que precisa para fazer uma compra e venda?",
        historico=[
            {
                "papel": "usuario",
                "conteudo": "Quais documentos são necessários para ata notarial?",
            },
            {"papel": "assistente", "conteudo": "Resposta sobre ata notarial."},
        ],
    )

    assert consultation_router._consulta_para_recuperacao(dados) == dados.consulta


def test_pergunta_de_testamento_nao_herda_doacao():
    dados = consultation_router.ConsultaRequest(
        consulta="E o que precisa para um testamento?",
        historico=[{"papel": "usuario", "conteudo": "Como fazer uma doação?"}],
    )

    assert consultation_router._consulta_para_recuperacao(dados) == dados.consulta


def test_pergunta_geral_prioriza_secao_central_sem_apagar_outro_documento():
    fontes = [
        {"documento_id": "codigo", "similaridade": 0.67, "artigo": "Art. 1.252"},
        {"documento_id": "codigo", "similaridade": 0.60, "artigo": "Art. 1.251"},
        {"documento_id": "codigo", "similaridade": 0.54, "artigo": "Art. 1.254"},
        {"documento_id": "codigo", "similaridade": 0.48, "artigo": "Art. 1.255"},
    ]
    priorizadas = consultation_router._priorizar_fontes_de_pergunta_geral(
        "Ata Notarial, o que precisa?", fontes
    )
    assert [item["artigo"] for item in priorizadas] == ["Art. 1.252", "Art. 1.251"]
    assert consultation_router._priorizar_fontes_de_pergunta_geral(
        "Ata Notarial, o que precisa?",
        [*fontes, {"documento_id": "entendimento", "similaridade": 0.40}],
    ) == [*fontes, {"documento_id": "entendimento", "similaridade": 0.40}]


def test_compra_venda_geral_inclui_regras_transversais_e_exclui_casos_especiais():
    fontes = [
        {
            "fonte_id": "FONTE-1193",
            "documento_id": "codigo",
            "artigo": "Art. 1.193",
            "conteudo": (
                "Art. 1.193. A escritura deve conter, quando for o caso, a forma e "
                "o meio de pagamento. A capacidade do comparecente será verificada."
            ),
            "similaridade": 0.39,
        },
        {
            "fonte_id": "FONTE-1198",
            "documento_id": "codigo",
            "artigo": "Art. 1.198",
            "conteudo": (
                "Art. 1.198. As escrituras públicas que tenham por objeto bens "
                "imóveis devem conter a matrícula, localização e os documentos "
                "exigidos para a transmissão."
            ),
            "similaridade": 0.38,
        },
        {
            "fonte_id": "FONTE-1201",
            "documento_id": "codigo",
            "artigo": "Art. 1.201",
            "conteudo": (
                "Art. 1.201. No ato translativo de imóvel, o tabelião exigirá prova "
                "dominial de quem pretende alienar o bem."
            ),
            "similaridade": 0.37,
        },
        {
            "fonte_id": "FONTE-821",
            "documento_id": "codigo",
            "artigo": "Art. 821",
            "conteudo": (
                "Art. 821. É defeso registrar compra e venda quando o numerário "
                "pertencer a menor incapaz sem autorização judicial."
            ),
            "similaridade": 0.70,
        },
        {
            "fonte_id": "FONTE-1202",
            "documento_id": "codigo",
            "artigo": "Art. 1.202",
            "conteudo": (
                "Art. 1.202. Em compra e venda de bem de pessoa falecida, o "
                "inventariante representa o espólio nas condições previstas."
            ),
            "similaridade": 0.68,
        },
    ]
    pergunta = "O que precisa para uma escritura de Compra e Venda?"

    filtradas = consultation_router._filtrar_resultados_por_tema(pergunta, fontes)
    priorizadas = consultation_router._priorizar_fontes_de_pergunta_geral(
        pergunta, filtradas
    )

    assert {item["artigo"] for item in priorizadas} == {
        "Art. 1.193",
        "Art. 1.198",
        "Art. 1.201",
    }


def test_compra_venda_especial_permanece_quando_a_pergunta_delimita_a_hipotese():
    fonte = {
        "fonte_id": "FONTE-821",
        "documento_id": "codigo",
        "artigo": "Art. 821",
        "conteudo": (
            "Art. 821. É defeso registrar compra e venda quando o numerário "
            "pertencer a menor incapaz sem autorização judicial."
        ),
        "similaridade": 0.8,
    }

    filtradas = consultation_router._filtrar_resultados_por_tema(
        "O que precisa para compra e venda quando o comprador é menor incapaz?",
        [fonte],
    )

    assert filtradas == [fonte]


def test_compra_venda_geral_descarta_hipotese_especial_com_acentos_normalizados():
    espolio = {
        "fonte_id": "FONTE-ESPOLIO",
        "documento_id": "codigo",
        "artigo": "Art. 1.202",
        "conteudo": (
            "Art. 1.202. O inventariante representa o espólio em transmissão "
            "contratada e liquidada em vida pelo falecido."
        ),
    }
    marinha = {
        "fonte_id": "FONTE-MARINHA",
        "documento_id": "codigo",
        "artigo": "Art. 1.198",
        "conteudo": (
            "Art. 1.198. Para imóveis em faixa de terrenos de marinha, a escritura de "
            "alienação deve mencionar a CAT e o recolhimento do laudêmio."
        ),
    }
    geral_urbano_rural = {
        "fonte_id": "FONTE-IMOVEL",
        "documento_id": "codigo",
        "artigo": "Art. 1.198",
        "conteudo": (
            "Art. 1.198. As escrituras de imóveis urbanos e rurais devem conter os dados "
            "necessários para a transmissão."
        ),
    }

    filtradas = consultation_router._filtrar_resultados_por_tema(
        "O que precisa para uma escritura de Compra e Venda?",
        [espolio, marinha, geral_urbano_rural],
    )

    assert filtradas == [geral_urbano_rural]


def test_continuacao_sem_numero_explicito_permanece_vinculada_a_artigo_confirmado():
    ancora = {
        "fonte_id": "FONTE-1198",
        "documento_id": "codigo",
        "artigo": "Art. 1.198",
        "artigo_contexto": "Art. 1.198",
        "conteudo": (
            "Art. 1.198. As escrituras públicas de bens imóveis devem conter "
            "os requisitos aplicáveis à transmissão."
        ),
    }
    continuacao = {
        "fonte_id": "FONTE-PAGINA-302",
        "documento_id": "codigo",
        "artigo": None,
        "artigo_contexto": "Art. 1.198",
        "conteudo": (
            "A certidão de inteiro teor e a prova de pagamento do imposto de "
            "transmissão serão apresentadas conforme a regra aplicável."
        ),
    }

    filtradas = consultation_router._filtrar_resultados_por_tema(
        "O que precisa para uma escritura de Compra e Venda?",
        [ancora, continuacao],
    )

    assert filtradas == [ancora, continuacao]
    assert continuacao["artigo"] is None


def test_consulta_ampla_compra_venda_busca_regras_gerais_e_responde_em_linguagem_pratica(
    client,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("compra-venda-sintese")
    fontes_especiais = [
        {
            "fonte_id": "FONTE-00000000-0000-0000-0000-000000000821",
            "chunk_id": "00000000-0000-0000-0000-000000000821",
            "documento_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "documento": "Código de Normas",
            "versao_documento": None,
            "pagina": 222,
            "localizacao": "Página 222",
            "posicao": 1,
            "artigo": "Art. 821",
            "capitulo": None,
            "secao": None,
            "paragrafo": None,
            "inciso": None,
            "conteudo": (
                "Art. 821. É defeso registrar compra e venda quando o numerário "
                "pertencer a menor incapaz sem autorização judicial."
            ),
            "similaridade": 0.8,
        },
        {
            "fonte_id": "FONTE-00000000-0000-0000-0000-000000001202",
            "chunk_id": "00000000-0000-0000-0000-000000001202",
            "documento_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "documento": "Código de Normas",
            "versao_documento": None,
            "pagina": 304,
            "localizacao": "Página 304",
            "posicao": 1,
            "artigo": "Art. 1.202",
            "capitulo": None,
            "secao": None,
            "paragrafo": None,
            "inciso": None,
            "conteudo": (
                "Art. 1.202. Em compra e venda de bem de pessoa falecida, o "
                "inventariante representa o espólio nas condições previstas."
            ),
            "similaridade": 0.78,
        },
    ]
    fontes_gerais = [
        {
            "fonte_id": "FONTE-00000000-0000-0000-0000-000000001193",
            "chunk_id": "00000000-0000-0000-0000-000000001193",
            "documento_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "documento": "Código de Normas",
            "versao_documento": None,
            "pagina": 300,
            "localizacao": "Página 300",
            "posicao": 1,
            "artigo": "Art. 1.193",
            "capitulo": None,
            "secao": None,
            "paragrafo": None,
            "inciso": None,
            "conteudo": (
                "Art. 1.193. A escritura deve indicar a forma e o meio de pagamento. "
                "A capacidade do comparecente será verificada pelo tabelião."
            ),
            "similaridade": 0.42,
        },
        {
            "fonte_id": "FONTE-00000000-0000-0000-0000-000000001198",
            "chunk_id": "00000000-0000-0000-0000-000000001198",
            "documento_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "documento": "Código de Normas",
            "versao_documento": None,
            "pagina": 301,
            "localizacao": "Página 301",
            "posicao": 1,
            "artigo": "Art. 1.198",
            "capitulo": None,
            "secao": None,
            "paragrafo": None,
            "inciso": None,
            "conteudo": (
                "Art. 1.198. As escrituras públicas de bens imóveis devem conter "
                "matrícula, localização e os documentos exigidos para a transmissão."
            ),
            "similaridade": 0.41,
        },
        {
            "fonte_id": "FONTE-00000000-0000-0000-0000-000000001201",
            "chunk_id": "00000000-0000-0000-0000-000000001201",
            "documento_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "documento": "Código de Normas",
            "versao_documento": None,
            "pagina": 304,
            "localizacao": "Página 304",
            "posicao": 1,
            "artigo": "Art. 1.201",
            "capitulo": None,
            "secao": None,
            "paragrafo": None,
            "inciso": None,
            "conteudo": (
                "Art. 1.201. No ato translativo de imóvel, o tabelião exigirá prova "
                "dominial de quem pretende alienar o bem."
            ),
            "similaridade": 0.40,
        },
    ]
    consultas_recebidas = []
    contexto_enviado = {}

    def buscar(_db, consulta, limite):
        consultas_recebidas.append(consulta)
        if "certidão de inteiro teor" in consulta or "prova dominial" in consulta:
            return fontes_gerais
        return fontes_especiais

    monkeypatch.setattr(consultation_router, "buscar_chunks_semelhantes", buscar)
    monkeypatch.setattr(
        consultation_router,
        "gerar_resposta",
        lambda *, pergunta, contexto, historico: contexto_enviado.update(
            contexto=contexto
        )
        or (
            "O tabelião deve conferir a prova dominial de quem pretende alienar o "
            "imóvel. [FONTE-00000000-0000-0000-0000-000000001201] A escritura de "
            "imóvel deve identificar a matrícula e a localização, além dos documentos "
            "exigidos para a transmissão. "
            "[FONTE-00000000-0000-0000-0000-000000001198] Também deve registrar a "
            "forma e o meio de pagamento, e a capacidade de cada comparecente deve "
            "ser verificada. [FONTE-00000000-0000-0000-0000-000000001193]"
        ),
    )

    resposta = client.post(
        "/api/consultar",
        headers=auth_headers(usuario),
        json={"consulta": "O que precisa para uma escritura de Compra e Venda?"},
    )

    assert resposta.status_code == 200
    dados = resposta.json()
    assert len(consultas_recebidas) == 5
    assert any("documentos exigidos requisitos checklist" in consulta for consulta in consultas_recebidas)
    assert "prova dominial" in consultas_recebidas[-1]
    assert "matrícula" in contexto_enviado["contexto"]
    assert "forma e o meio de pagamento" in contexto_enviado["contexto"]
    assert "Art. 821" not in contexto_enviado["contexto"]
    assert "Art. 1.202" not in contexto_enviado["contexto"]
    assert dados["situacao_resposta"] == "EVIDENCIA_SUFFICIENTE"
    assert "O tabelião deve conferir a prova dominial" in dados["resposta"]
    assert "Fundamentação: Código de Normas, arts. 1.201, 1.198 e 1.193." in dados[
        "resposta"
    ]


def test_consulta_ampla_inventario_busca_e_cita_documento_ficticio(
    client,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("inventario-sintetico")
    fonte_id = "FONTE-33333333-3333-3333-3333-333333333333"
    fonte_ficticia = {
        "fonte_id": fonte_id,
        "chunk_id": "33333333-3333-3333-3333-333333333333",
        "documento_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
        "documento": "Fixture fictícia — sem valor normativo",
        "versao_documento": "teste",
        "pagina": 1,
        "localizacao": "Trecho sintético 1",
        "posicao": 1,
        "artigo": "Art. 99",
        "capitulo": None,
        "secao": None,
        "paragrafo": None,
        "inciso": None,
        "conteudo": (
            "Art. 99. O documento fictício de inventário extrajudicial descreve "
            "certidão de óbito, relação de herdeiros e documentos pessoais."
        ),
        "similaridade": 0.91,
    }
    consultas_recebidas = []
    contexto_enviado = {}

    def buscar(_db, consulta, limite):
        consultas_recebidas.append(consulta)
        return [fonte_ficticia]

    def responder(*, pergunta, contexto, historico):
        contexto_enviado["texto"] = contexto
        return (
            "O documento fictício de inventário extrajudicial descreve certidão "
            "de óbito, relação de herdeiros e documentos pessoais."
        )

    monkeypatch.setattr(consultation_router, "buscar_chunks_semelhantes", buscar)
    monkeypatch.setattr(consultation_router, "gerar_resposta", responder)

    resposta = client.post(
        "/api/consultar",
        headers=auth_headers(usuario),
        json={"consulta": "O que precisa para um inventário extrajudicial?"},
    )

    assert resposta.status_code == 200
    dados = resposta.json()
    assert len(consultas_recebidas) == 6
    assert any("documentos exigidos requisitos checklist" in consulta for consulta in consultas_recebidas)
    assert any("certidão de óbito" in consulta for consulta in consultas_recebidas)
    assert "relação de herdeiros" in contexto_enviado["texto"]
    assert dados["situacao_resposta"] == "EVIDENCIA_SUFFICIENTE"
    assert dados["citacoes_verificadas"] == [fonte_id]
    assert "Fixture fictícia — sem valor normativo" in dados["resposta"]
    assert "Art. 99" in dados["resposta"]


def test_checklist_documental_e_resumido_com_fonte_integral(
    db,
    usuario_factory,
    monkeypatch,
):
    admin = usuario_factory("admin-checklist-sintetico", role="ADMIN")
    documento = Documento(
        titulo="Checklist de Compra e Venda",
        tipo="MANUAL",
        situacao="APROVADO",
        nome_arquivo="checklist-sintetico.txt",
        caminho_arquivo="nao-utilizado",
        criado_por=admin.id,
        status="PRONTO",
        status_seguranca="LIBERADO",
        situacao_extracao="PROCESSADO_COMPLETO",
    )
    db.add(documento)
    db.flush()
    conteudo = (
        "Vendedor:\n"
        "- Documento pessoal e CPF.\n"
        "- Certidão de estado civil atualizada.\n"
        "Comprador:\n"
        "- Documento pessoal e CPF.\n"
        "- Comprovante de endereço."
    )
    db.add(
        DocumentoPagina(
            documento_id=documento.id,
            pagina=1,
            conteudo=conteudo,
        )
    )
    db.commit()
    fonte = {
        "fonte_id": "FONTE-11111111-1111-1111-1111-111111111111",
        "chunk_id": "11111111-1111-1111-1111-111111111111",
        "documento_id": str(documento.id),
        "documento": documento.titulo,
        "versao_documento": None,
        "pagina": 1,
        "localizacao": "Página 1",
        "posicao": 1,
        "artigo": None,
        "conteudo": conteudo,
        "similaridade": 0.9,
    }
    chamadas = []

    def gerar_resumo(**kwargs):
        chamadas.append(kwargs)
        assert "Vendedor:" in kwargs["contexto"]
        assert "Comprador:" in kwargs["contexto"]
        return (
            "Para compra e venda, confira a identificação e o CPF de vendedor e "
            "comprador, a certidão atualizada de estado civil do vendedor e o "
            "comprovante de endereço do comprador. [FONTE-1]"
        )

    monkeypatch.setattr(consultation_router, "gerar_resposta", gerar_resumo)

    resultado = consultation_router._responder_com_checklist_da_fonte(
        db,
        "O que preciso para compra e venda?",
        [fonte],
    )

    assert resultado is not None
    resposta, fontes_usadas, citacoes, metodo = resultado
    assert "confira a identificação e o CPF de vendedor e comprador" in resposta
    assert "Certidão de estado civil atualizada" not in resposta
    assert "comprovante de endereço" in resposta
    assert len(citacoes) == 1
    assert fontes_usadas[0]["chunk_id"] is None
    assert metodo == "resumo_checklist_ollama"
    assert len(chamadas) == 1
    assert chamadas[0]["resumir_checklist"] is True
    assert "Documento pessoal e CPF" in chamadas[0]["contexto"]


def test_checklist_sem_sintese_validada_nao_e_substituido_por_copia_literal(
    db,
    usuario_factory,
    monkeypatch,
):
    admin = usuario_factory("admin-checklist-invalido", role="ADMIN")
    documento = Documento(
        titulo="Checklist de Compra e Venda",
        tipo="MANUAL",
        situacao="APROVADO",
        nome_arquivo="checklist-sintetico.txt",
        caminho_arquivo="nao-utilizado",
        criado_por=admin.id,
        status="PRONTO",
        status_seguranca="LIBERADO",
        situacao_extracao="PROCESSADO_COMPLETO",
    )
    db.add(documento)
    db.flush()
    conteudo = (
        "Vendedor:\n"
        "- Documento pessoal e CPF.\n"
        "- Certidão de estado civil atualizada.\n"
        "Comprador:\n"
        "- Documento pessoal e CPF.\n"
        "- Comprovante de endereço."
    )
    db.add(DocumentoPagina(documento_id=documento.id, pagina=1, conteudo=conteudo))
    db.commit()
    fonte = {
        "fonte_id": "FONTE-22222222-2222-2222-2222-222222222222",
        "chunk_id": "22222222-2222-2222-2222-222222222222",
        "documento_id": str(documento.id),
        "documento": documento.titulo,
        "versao_documento": None,
        "pagina": 1,
        "localizacao": "Página 1",
        "posicao": 1,
        "artigo": None,
        "conteudo": conteudo,
        "similaridade": 0.9,
    }
    monkeypatch.setattr(
        consultation_router,
        "gerar_resposta",
        lambda **kwargs: "A resposta é sim.",
    )

    resultado = consultation_router._responder_com_checklist_da_fonte(
        db,
        "O que preciso para compra e venda?",
        [fonte],
    )

    assert resultado is not None
    resposta, _, citacoes, metodo = resultado
    assert resposta == consultation_router.RESPOSTA_BASE_INSUFICIENTE
    assert citacoes == []
    assert metodo == "checklist_resumo_nao_validado"
    assert "Documento pessoal e CPF" not in resposta


def test_resposta_parcial_reune_itens_de_lista_sem_fragmentar_a_frase():
    resposta = consultation_router._formatar_afirmacoes_parciais(
        [
            ("A ata notarial conterá: local, data e hora do fato", FONTE_ID),
            ("nome e qualificação do solicitante", FONTE_ID),
            ("narração circunstanciada dos fatos", FONTE_ID),
            ("Pode ser eletrônica", FONTE_ID),
        ],
        {
            FONTE_ID: {
                "documento": "Código de Normas",
                "artigo": "Art. 1.252",
                "conteudo": "A ata notarial conterá local, data e hora do fato.",
            }
        },
    )
    assert "fato; nome e qualificação do solicitante; narração" in resposta
    assert "fato. nome" not in resposta


def test_resposta_parcial_tambem_reune_itens_sem_dois_pontos():
    resposta = consultation_router._formatar_afirmacoes_parciais(
        [
            ("A ata notarial conterá local, data e hora do fato", FONTE_ID),
            ("nome e qualificação do solicitante", FONTE_ID),
        ],
        {
            FONTE_ID: {
                "documento": "Código de Normas",
                "artigo": "Art. 1.252",
                "conteudo": "A ata notarial conterá local, data e hora do fato.",
            }
        },
    )
    assert "fato; nome e qualificação" in resposta


def test_pergunta_de_doacao_iniciada_com_conjuncao_nao_herda_ata_notarial():
    dados = consultation_router.ConsultaRequest(
        consulta="E o que precisa para uma doação?",
        historico=[
            {
                "papel": "usuario",
                "conteudo": "Quais documentos são necessários para ata notarial?",
            },
            {"papel": "assistente", "conteudo": "Resposta sobre ata notarial."},
        ],
    )

    recuperacao = consultation_router._consulta_para_recuperacao(dados)

    assert "doação" in recuperacao
    assert "ata notarial" not in recuperacao


def test_consulta_filtra_fontes_de_outro_ato():
    fontes = [
        {
            "documento_id": "doc-1",
            "artigo": "Art. 1.210",
            "conteudo": "Art. 1.210. A doação é aceita pelo donatário.",
        },
        {
            "documento_id": "doc-1",
            "artigo": "Art. 1.252",
            "conteudo": "Art. 1.252. A ata notarial conterá local e data.",
        },
    ]

    resultado = consultation_router._filtrar_resultados_por_tema(
        "E o que precisa para uma doação?", fontes
    )

    assert [item["artigo"] for item in resultado] == ["Art. 1.210"]


def test_consulta_sem_trecho_do_tema_nao_reutiliza_fonte_de_outro_assunto():
    fontes = [
        {
            "documento_id": "doc-1",
            "artigo": "Art. 1.252",
            "conteudo": "Art. 1.252. A ata notarial conterá local e data.",
        },
    ]

    assert (
        consultation_router._filtrar_resultados_por_tema(
            "O que precisa para uma doação?", fontes
        )
        == []
    )


def test_filtro_tematico_ignora_mencao_em_artigo_vizinho_ou_especifico():
    fontes = [
        {
            "documento_id": "doc-1",
            "artigo": "Art. 1.208",
            "conteudo": (
                "Art. 1.208. Regra de condomínio rural.\n"
                "Subseção III Escritura Pública de Doação"
            ),
        },
        {
            "documento_id": "doc-1",
            "artigo": "Art. 1.212",
            "conteudo": (
                "Art. 1.212. A renúncia do usufruto será lavrada quando decidida. "
                "O recolhimento do Imposto de Transmissão Causa Mortis e Doação "
                "(ITCMD) observará a legislação de regência."
            ),
        },
    ]

    assert (
        consultation_router._filtrar_resultados_por_tema(
            "O que precisa para uma doação?", fontes
        )
        == []
    )


def test_busca_de_doacao_nao_recebe_historico_de_ata_notarial(
    client,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("doacao-sem-contaminacao")
    consultas_recebidas = []
    monkeypatch.setattr(
        consultation_router,
        "buscar_chunks_semelhantes",
        lambda db, consulta, limite: consultas_recebidas.append(consulta) or [],
    )

    resposta = client.post(
        "/api/consultar",
        headers=auth_headers(usuario),
        json={
            "consulta": "E o que precisa para uma doação?",
            "historico": [
                {
                    "papel": "usuario",
                    "conteudo": "Quais documentos são necessários para ata notarial?",
                }
            ],
        },
    )

    assert resposta.status_code == 200
    assert consultas_recebidas
    assert all(
        "ata notarial" not in consulta.casefold() for consulta in consultas_recebidas
    )
    assert "doação" in consultas_recebidas[0]


def test_pergunta_de_continuidade_nao_reescreve_o_assunto_anterior():
    dados = consultation_router.ConsultaRequest(
        consulta="E quanto ao prazo?",
        historico=[
            {
                "papel": "usuario",
                "conteudo": "Como funciona a certidão de casamento?",
            },
            {"papel": "assistente", "conteudo": "Resposta anterior não é evidência."},
        ],
    )

    recuperacao = consultation_router._consulta_para_recuperacao(dados)

    assert "certidão de casamento" in recuperacao
    assert "E quanto ao prazo?" in recuperacao
    assert "Resposta anterior não é evidência." not in recuperacao


def test_citacao_com_numero_conflitante_nao_e_validada():
    resultados = [
        {
            "fonte_id": FONTE_ID,
            "documento": "Norma controlada",
            "pagina": 1,
            "localizacao": "Página 1",
            "artigo": "Art. 10",
            "conteudo": "A certidão deve ter sido emitida há no máximo 90 dias.",
        }
    ]

    resposta, citacoes, situacao = consultation_router._garantir_citacoes(
        f"A certidão possui validade de 30 dias. [{FONTE_ID}]",
        resultados,
    )

    assert citacoes == []
    assert situacao == "BASE_INSUFICIENTE"
    assert "Norma controlada" not in resposta


def test_citacao_com_apenas_um_termo_generico_nao_e_validada():
    resultados = [
        {
            "fonte_id": FONTE_ID,
            "documento": "Norma controlada",
            "pagina": 1,
            "localizacao": "Página 1",
            "artigo": "Art. 10",
            "conteudo": "A certidão deve ser apresentada no prazo regulamentar.",
        }
    ]

    resposta, citacoes, situacao = consultation_router._garantir_citacoes(
        f"A certidão autoriza alienação sem representação. [{FONTE_ID}]",
        resultados,
    )

    assert citacoes == []
    assert situacao == "BASE_INSUFICIENTE"
    assert "evidência direta suficiente" in resposta


def test_citacao_nao_generaliza_regra_de_procedimento_especifico():
    fonte = {
        "conteudo": (
            "No procedimento de adjudicação compulsória extrajudicial, o "
            "requerimento inicial será instruído por ata notarial e pelo "
            "instrumento do ato ou negócio jurídico que funda o pedido."
        )
    }

    assert not consultation_router._citacao_tem_apoio(
        "Para toda cessão, é necessário apresentar ata notarial e o instrumento "
        "do negócio jurídico.",
        fonte,
    )
    assert consultation_router._citacao_tem_apoio(
        "No procedimento de adjudicação compulsória extrajudicial, o requerimento "
        "inicial deve ser instruído por ata notarial e pelo instrumento do negócio.",
        fonte,
    )


def test_afirmacao_sem_fonte_nao_e_exibida_como_resposta_parcial():
    resultados = [
        {
            "fonte_id": FONTE_ID,
            "documento": "Norma controlada",
            "pagina": 1,
            "localizacao": "Página 1",
            "artigo": "Art. 10",
            "conteudo": "A certidão possui validade de 90 dias.",
        }
    ]

    resposta, citacoes, situacao = consultation_router._garantir_citacoes(
        "A autorização judicial é dispensada. "
        f"A certidão possui validade de 90 dias. [{FONTE_ID}]",
        resultados,
    )

    assert citacoes == [FONTE_ID]
    assert situacao == "EVIDENCIA_PARCIAL"
    assert "autorização judicial é dispensada" not in resposta
    assert "validade de 90 dias" in resposta


def test_citacao_com_negacao_contraditoria_nao_e_validada():
    resultados = [
        {
            "fonte_id": FONTE_ID,
            "documento": "Norma controlada",
            "pagina": 1,
            "localizacao": "Página 1",
            "artigo": "Art. 10",
            "conteudo": "A autorização judicial é necessária para o ato.",
        }
    ]

    _, citacoes, situacao = consultation_router._garantir_citacoes(
        f"A autorização judicial não é necessária para o ato. [{FONTE_ID}]",
        resultados,
    )

    assert citacoes == []
    assert situacao == "BASE_INSUFICIENTE"


def test_citacao_valida_regra_positiva_com_negacao_em_paragrafo_vizinho():
    resultados = [
        {
            "fonte_id": FONTE_ID,
            "documento": "Código de Normas",
            "pagina": 315,
            "localizacao": "Capítulo V, Seção I",
            "artigo": "Art. 1.252",
            "conteudo": (
                "Art. 1.252. A ata notarial conterá: I – local, data e hora do fato; "
                "II – nome e qualificação do solicitante; III – narração circunstanciada "
                "dos fatos; IV – declaração de haver sido lida ao solicitante; V – "
                "assinatura do solicitante ou certificação da solicitação; VI – sinal "
                "público. § 1º O conteúdo pode versar sobre quaisquer ocorrências, "
                "não apenas vistorias em objetos e lugares."
            ),
        }
    ]

    resposta, citacoes, situacao = consultation_router._garantir_citacoes(
        f"A ata notarial conterá o local, a data e a hora do fato. [{FONTE_ID}]",
        resultados,
    )

    assert citacoes == [FONTE_ID]
    assert situacao == "EVIDENCIA_SUFFICIENTE"
    assert "Fundamentação: Código de Normas, Art. 1.252." in resposta
    assert resposta.count("1.252") == 1


def test_referencias_sao_reunidas_ao_final_sem_citacao_no_corpo():
    resultados = [
        {
            "fonte_id": FONTE_ID,
            "documento": "Código de Normas",
            "pagina": 261,
            "localizacao": "Página 261",
            "artigo": None,
            "conteudo": (
                "A qualificação e o endereço do requerente e do requerido seguem "
                "o art. 287."
            ),
        }
    ]

    resposta, citacoes, situacao = consultation_router._garantir_citacoes(
        f"Conforme art. 287, devem constar a qualificação e o endereço do "
        f"requerente e do requerido. [{FONTE_ID}]",
        resultados,
    )

    assert citacoes == [FONTE_ID]
    assert situacao == "EVIDENCIA_SUFFICIENTE"
    assert "art. 287" not in resposta.casefold()
    assert resposta.endswith("Fundamentação: Código de Normas, página 261.")


def test_fundamentacao_agrupa_artigos_e_paginas_do_mesmo_documento():
    fontes = {
        FONTE_ID: {
            "documento": "Código de Normas",
            "artigo": "Art. 1.214",
            "pagina": 306,
            "localizacao": "Página 306",
        },
        "FONTE-22222222-2222-2222-2222-222222222222": {
            "documento": "Código de Normas",
            "artigo": "Art. 1.213",
            "pagina": 306,
            "localizacao": "Página 306",
        },
        "FONTE-33333333-3333-3333-3333-333333333333": {
            "documento": "Código de Normas",
            "artigo": None,
            "pagina": 261,
            "localizacao": "Página 261",
        },
    }

    resposta = consultation_router._formatar_fundamentacao(list(fontes), fontes)

    assert resposta == (
        "Fundamentação: Código de Normas, arts. 1.214 e 1.213, página 261."
    )


def test_citacoes_em_frases_sequenciais_no_mesmo_paragrafo_validam_cobertura():
    resultados = [
        {
            "fonte_id": FONTE_ID,
            "documento": "Código de Normas",
            "pagina": 315,
            "localizacao": "Capítulo V, Seção I",
            "artigo": "Art. 1.252",
            "conteudo": (
                "A ata notarial conterá o local e a data do fato. "
                "A ata notarial conterá o nome e a qualificação do solicitante."
            ),
        }
    ]

    resposta, citacoes, situacao = consultation_router._garantir_citacoes(
        "A ata notarial conterá o local e a data do fato. "
        f"[{FONTE_ID}] A ata notarial conterá o nome e a qualificação do solicitante. "
        f"[{FONTE_ID}]",
        resultados,
    )

    assert citacoes == [FONTE_ID]
    assert situacao == "EVIDENCIA_SUFFICIENTE"
    assert "Fundamentação: Código de Normas, Art. 1.252." in resposta
    assert resposta.count("1.252") == 1


def test_consulta_preserva_apenas_afirmacoes_citadas_e_apoiadas_em_resposta_parcial():
    resultados = [
        {
            "fonte_id": FONTE_ID,
            "documento": "Código de Normas",
            "pagina": 315,
            "localizacao": "Capítulo V, Seção I",
            "artigo": "Art. 1.252",
            "conteudo": "A ata notarial conterá local, data e hora do fato.",
        }
    ]
    resposta_modelo = (
        "Elementos aplicáveis:\n"
        f"A ata notarial conterá local, data e hora do fato. [{FONTE_ID}]\n\n"
        f"É obrigatório apresentar RG e comprovante de endereço. [{FONTE_ID}]"
    )

    resposta, citacoes, situacao = consultation_router._garantir_citacoes(
        resposta_modelo,
        resultados,
    )

    assert citacoes == [FONTE_ID]
    assert situacao == "EVIDENCIA_PARCIAL"
    assert "local, data e hora do fato" in resposta
    assert "obrigatório apresentar RG" not in resposta
    assert "[FONTE-" not in resposta
    assert "Fundamentação: Código de Normas, Art. 1.252." in resposta
    assert "não confirma um checklist completo" in resposta
    assert resposta.count("1.252") == 1
    assert not resposta.lstrip().startswith("-")


def test_citacao_nao_confunde_negacao_em_clausula_nao_relacionada():
    fonte = {
        "fonte_id": FONTE_ID,
        "documento": "Norma controlada",
        "pagina": 1,
        "localizacao": "Art. 1",
        "artigo": "Art. 1",
        "conteudo": (
            "A autorização judicial é necessária para a venda. A certidão não "
            "dispensa a identificação das partes."
        ),
    }

    assert consultation_router._citacao_tem_apoio(
        "A autorização judicial é necessária para a venda.", fonte
    )


def test_citacao_nao_valida_checklist_nao_presente_no_artigo_de_ata():
    fonte = {
        "fonte_id": FONTE_ID,
        "documento": "Código de Normas",
        "pagina": 315,
        "localizacao": "Capítulo V, Seção I",
        "artigo": "Art. 1.252",
        "conteudo": (
            "Art. 1.252. A ata notarial conterá local, data e hora do fato, "
            "nome e qualificação do solicitante e narração circunstanciada dos fatos."
        ),
    }

    assert not consultation_router._citacao_tem_apoio(
        "Para solicitar ata notarial, apresente RG, CPF e comprovante de endereço.",
        fonte,
    )


def test_citacao_valida_artigo_com_numero_decimal_sem_fragmentar_a_afirmacao():
    resultados = [
        {
            "fonte_id": FONTE_ID,
            "documento": "Código de Normas",
            "pagina": 320,
            "localizacao": "Página 320",
            "artigo": "Art. 1.277",
            "conteudo": (
                "Art. 1.277. Para a abertura da ficha padrão, é obrigatória a "
                "apresentação do original de documento de identificação com foto, "
                "sendo admitidos: cédula de identidade; passaporte; carteira nacional "
                "de habilitação; carteira de identidade militar."
            ),
        }
    ]

    resposta, citacoes, situacao = consultation_router._garantir_citacoes(
        "Para a abertura da ficha-padrão, o art. 1.277 admite cédula de identidade, "
        f"passaporte, carteira nacional de habilitação e identidade militar. [{FONTE_ID}]",
        resultados,
    )

    assert citacoes == [FONTE_ID]
    assert situacao == "EVIDENCIA_SUFFICIENTE"
    assert "Código de Normas, Art. 1.277" in resposta


def test_citacao_ao_final_da_lista_cobre_apenas_itens_apoiados_pela_mesma_fonte():
    resultados = [
        {
            "fonte_id": FONTE_ID,
            "documento": "Código de Normas",
            "pagina": 320,
            "localizacao": "Página 320",
            "artigo": "Art. 1.277",
            "conteudo": (
                "Para ficha padrão, são admitidos cédula de identidade e passaporte."
            ),
        }
    ]

    resposta, citacoes, situacao = consultation_router._garantir_citacoes(
        "Para a ficha padrão, são admitidos cédula de identidade e passaporte. "
        f"[{FONTE_ID}]",
        resultados,
    )

    assert citacoes == [FONTE_ID]
    assert situacao == "EVIDENCIA_SUFFICIENTE"
    assert "Art. 1.277" in resposta


def test_citacao_ao_final_da_lista_nao_cobre_item_sem_apoio_na_fonte():
    resultados = [
        {
            "fonte_id": FONTE_ID,
            "documento": "Código de Normas",
            "pagina": 320,
            "localizacao": "Página 320",
            "artigo": "Art. 1.277",
            "conteudo": "Para ficha padrão, são admitidos cédula de identidade e passaporte.",
        }
    ]

    resposta, citacoes, situacao = consultation_router._garantir_citacoes(
        "Para a ficha padrão, são admitidos cédula de identidade, passaporte e "
        f"certidão de nascimento. [{FONTE_ID}]",
        resultados,
    )

    assert citacoes == []
    assert situacao == "BASE_INSUFICIENTE"
    assert "evidência direta suficiente" in resposta
