from datetime import date, datetime

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


def test_consulta_nao_atribui_fonte_quando_modelo_nao_cita(
    client,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    usuario = usuario_factory("sem-citacao")
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
            }
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
    assert resposta.json()["citacoes_verificadas"] == []
    assert resposta.json()["resultados"] == []
    assert resposta.json()["situacao_resposta"] == "BASE_INSUFICIENTE"
    assert "evidência direta suficiente" in resposta.json()["resposta"]
    historico = client.get(
        "/api/consultar/historico",
        headers=auth_headers(usuario),
    ).json()["items"]
    assert historico[0]["fontes"][0]["citada"] is False
    assert historico[0]["fontes"][0]["recuperada"] is True


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
    assert dados["situacao_resposta"] == "BASE_INSUFICIENTE"
    assert dados["confiavel"] is False
    assert dados["citacoes_verificadas"] == []
    assert dados["resultados"] == []
    assert "português claro e direto" in dados["resposta"]
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
