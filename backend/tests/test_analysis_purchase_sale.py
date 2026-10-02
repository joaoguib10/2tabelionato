"""Compra e Venda: extração, edição humana e snapshot A1."""

from uuid import uuid4

from app.models import (
    Caso,
    CasoDocumento,
    CasoDocumentoPagina,
    Documento,
    DocumentoChunk,
)
from app.services import purchase_sale_service as compra_venda
from app.services.case_legal_analysis_service import _estado_atual


def _caso(db, usuario, *, responsavel=None):
    item = Caso(
        titulo="Compra e Venda sintética",
        tipo_ato="COMPRA_VENDA",
        criado_por=usuario.id,
        responsavel_id=responsavel,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _documento_pronto(db, caso, usuario):
    documento = CasoDocumento(
        caso_id=caso.id,
        nome_arquivo="certidao-sintetica.txt",
        caminho_arquivo="arquivo-sintetico-nao-real.txt",
        hash_arquivo="a" * 64,
        tipo_documento="CERTIDAO_CASAMENTO",
        vinculo_ato="VENDEDOR",
        status="PRONTO",
        status_seguranca="LIBERADO",
        situacao_extracao="PROCESSADO_COMPLETO",
        criado_por=usuario.id,
    )
    db.add(documento)
    db.flush()
    db.add(
        CasoDocumentoPagina(
            caso_documento_id=documento.id,
            pagina=1,
            pagina_confiavel=True,
            localizacao="Página 1",
            conteudo="JOAO TESTE, CPF 111.222.333-44, casado sob comunhao parcial.",
            metodo_extracao="TEXTO",
            situacao_extracao="PROCESSADO_COMPLETO",
        )
    )
    db.commit()
    return documento


def test_qualificacao_expoe_pendencias_sem_bloquear_e_descricao_obedece_regra():
    parte_id = uuid4()
    dados = compra_venda.dados_vazios()
    dados["partes"] = [
        {
            "id": str(parte_id),
            "papel": "VENDEDOR",
            "natureza": "FISICA",
            "participacao": "PRINCIPAL",
            "modo_qualificacao": "INDIVIDUAL",
            "nome_completo": "Pessoa Sintética",
            "cpf": "111",
            "estado_civil": "solteiro",
            "nacionalidade": "brasileiro",
            "capacidade": "maior e capaz",
            "profissao": None,
            "endereco": None,
            "uniao_estavel": False,
            "casamento": {},
            "empresa": {},
            "procuracao": {},
            "fontes": [],
            "origem": "MANUAL",
            "confirmado": False,
        }
    ]
    dados["imovel"].update(
        {
            "logradouro": "Rua Teste",
            "numero": "10",
            "bairro": "Centro",
            "cidade": "Cidade Sintética",
            "descricao_completa": "Descrição integral sintética.",
        }
    )
    qualificacoes, pendencias = compra_venda.gerar_qualificacoes(dados)
    assert "não convive em união estável" in qualificacoes[0]["texto"]
    assert "profissão" in qualificacoes[0]["pendencias"]
    assert "endereço" in qualificacoes[0]["pendencias"]
    assert dados["imovel"]["descricao_utilizada"].startswith("Rua Teste")
    assert pendencias
    dados["imovel"]["bairro"] = None
    compra_venda.atualizar_descricao_imovel(dados["imovel"])
    assert dados["imovel"]["descricao_utilizada"] == "Descrição integral sintética."


def test_mesclagem_nao_sobrescreve_valor_humano_confirmado():
    dados = compra_venda.dados_vazios()
    dados["partes"] = [
        {
            "id": str(uuid4()),
            "papel": "VENDEDOR",
            "natureza": "FISICA",
            "participacao": "PRINCIPAL",
            "principal_id": None,
            "modo_qualificacao": "INDIVIDUAL",
            "nome_completo": "Nome Humano",
            "cpf": "123",
            "estado_civil": "casado",
            "nacionalidade": "brasileiro",
            "capacidade": None,
            "profissao": "Oficial",
            "endereco": None,
            "uniao_estavel": None,
            "casamento": {},
            "empresa": {},
            "procuracao": {},
            "fontes": [],
            "origem": "MANUAL",
            "confirmado": True,
        }
    ]
    sugestao = {
        "partes": [
            {
                "nome_completo": "Outro Nome",
                "cpf": "123",
                "profissao": "Inventada",
                "fontes": [],
            }
        ],
        "imovel": {},
    }
    resultado = compra_venda.mesclar_sugestoes(dados, sugestao)
    assert resultado["partes"][0]["nome_completo"] == "Nome Humano"
    assert resultado["partes"][0]["profissao"] == "Oficial"


def test_qualificacoes_casal_empresa_e_procuracao_preservam_modelos_aprovados():
    principal_id, conjuge_id, empresa_id, representante_id, procurador_id = [
        uuid4() for _ in range(5)
    ]
    base = {
        "papel": "VENDEDOR",
        "natureza": "FISICA",
        "principal_id": None,
        "nome_completo": "Pessoa Sintética",
        "nacionalidade": "brasileiro(a)",
        "capacidade": "maior e capaz",
        "estado_civil": "casado",
        "profissao": "profissão teste",
        "cpf": "111",
        "endereco": "endereço teste",
        "uniao_estavel": None,
        "casamento": {},
        "empresa": {},
        "procuracao": {},
        "fontes": [],
        "origem": "MANUAL",
        "confirmado": True,
    }
    partes = [
        {
            **base,
            "id": str(principal_id),
            "participacao": "PRINCIPAL",
            "modo_qualificacao": "CASAL_COM_ANUENTE",
            "casamento": {
                "data_registro": "01/01/2020",
                "regime_bens": "comunhão parcial",
                "data_certidao": "02/02/2026",
                "selo_digital": "SELO-TESTE",
            },
        },
        {
            **base,
            "id": str(conjuge_id),
            "nome_completo": "Cônjuge Sintético",
            "participacao": "ANUENTE",
            "principal_id": str(principal_id),
            "modo_qualificacao": "INDIVIDUAL",
        },
        {
            **base,
            "id": str(empresa_id),
            "nome_completo": "Empresa Sintética Ltda.",
            "natureza": "JURIDICA",
            "participacao": "PRINCIPAL",
            "modo_qualificacao": "EMPRESA_REPRESENTADA",
            "empresa": {
                "cnpj": "00",
                "nire": "11",
                "endereco": "sede teste",
                "clausula_poderes": "5",
                "descricao_poderes": "poderes expressos",
            },
        },
        {
            **base,
            "id": str(representante_id),
            "nome_completo": "Representante Sintético",
            "participacao": "REPRESENTANTE",
            "principal_id": str(empresa_id),
            "modo_qualificacao": "INDIVIDUAL",
        },
        {
            **base,
            "id": str(procurador_id),
            "nome_completo": "Procurador Sintético",
            "participacao": "PROCURADOR",
            "modo_qualificacao": "PROCURACAO",
            "procuracao": {
                "lavrada_em": "01/01/2026",
                "livro": "1",
                "folhas": "2",
                "tabelionato": "Tabelionato Teste",
                "cidade_comarca": "Cidade Teste",
                "certidao_emitida_em": "03/03/2026",
                "selo_digital": "SELO-PROC",
            },
        },
    ]
    qualificacoes, _ = compra_venda.gerar_qualificacoes(
        {"partes": partes, "imovel": compra_venda.dados_vazios()["imovel"]}
    )
    textos = {item["parte_id"]: item["texto"] for item in qualificacoes}
    assert "na qualidade de interveniente anuente" in textos[str(principal_id)]
    assert "Cônjuge Sintético" in textos[str(principal_id)]
    assert "Representante Sintético" in textos[str(empresa_id)]
    assert "poderes conferidos pela cláusula 5" in textos[str(empresa_id)]
    assert "procuração lavrada em 01/01/2026" in textos[str(procurador_id)]


def test_api_salva_dados_por_responsavel_e_rejeita_fonte_de_outro_caso(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    criador = usuario_factory("criador-cv", role="ADMIN")
    responsavel = usuario_factory("responsavel-cv")
    caso = _caso(db, criador, responsavel=responsavel.id)
    outro = _caso(db, criador)
    documento_outro = _documento_pronto(db, outro, criador)
    payload = {
        "partes": [],
        "imovel": {
            "fontes": [
                {
                    "documento_id": str(documento_outro.id),
                    "pagina": 1,
                    "localizacao": "Página 1",
                    "trecho": "Trecho sintético",
                }
            ]
        },
    }
    url = f"/api/analises/casos/{caso.id}/compra-venda"
    assert (
        client.put(url, headers=auth_headers(responsavel), json=payload).status_code
        == 422
    )
    payload = {
        "partes": [
            {
                "id": str(uuid4()),
                "papel": "COMPRADOR",
                "nome_completo": "Pessoa Sintética",
                "cpf": "111",
                "estado_civil": "solteiro",
                "fontes": [],
            }
        ],
        "imovel": {"matricula": "1-SINTETICA"},
    }
    resposta = client.put(url, headers=auth_headers(responsavel), json=payload)
    assert resposta.status_code == 200
    assert resposta.json()["partes"][0]["nome_completo"] == "Pessoa Sintética"
    assert resposta.json()["partes"][0]["papel"] == "OUTORGADO"
    assert resposta.json()["pendencias"]


def test_extracao_descarta_fonte_inventada_e_nao_alimenta_rag(
    client,
    db,
    usuario_factory,
    auth_headers,
    monkeypatch,
):
    admin = usuario_factory("admin-cv", role="ADMIN")
    caso = _caso(db, admin)
    _documento_pronto(db, caso, admin)
    monkeypatch.setattr(
        compra_venda,
        "_gerar_dados",
        lambda _: {
            "partes": [
                {
                    "papel": "VENDEDOR",
                    "nome_completo": "JOAO TESTE",
                    "cpf": "111.222.333-44",
                    "trecho_fonte": "JOAO TESTE, CPF 111.222.333-44",
                },
                {
                    "papel": "COMPRADOR",
                    "nome_completo": "INVENTADO",
                    "trecho_fonte": "texto inexistente",
                },
            ],
            "imovel": {"averbacoes": []},
        },
    )
    resposta = client.post(
        f"/api/analises/casos/{caso.id}/compra-venda/extrair",
        headers=auth_headers(admin),
    )
    assert resposta.status_code == 202
    consulta = client.get(
        f"/api/analises/casos/{caso.id}/compra-venda",
        headers=auth_headers(admin),
    )
    assert consulta.status_code == 200
    assert [item["nome_completo"] for item in consulta.json()["partes"]] == [
        "JOAO TESTE"
    ]
    assert db.query(Documento).count() == 0
    assert db.query(DocumentoChunk).count() == 0


def test_estado_estruturado_confirmado_libera_a1_mesmo_com_campos_ausentes(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    admin = usuario_factory("admin-gate-cv", role="ADMIN")
    caso = _caso(db, admin)
    _documento_pronto(db, caso, admin)
    parte = {
        "id": str(uuid4()),
        "papel": "VENDEDOR",
        "natureza": "FISICA",
        "participacao": "PRINCIPAL",
        "principal_id": None,
        "modo_qualificacao": "INDIVIDUAL",
        "nome_completo": "Pessoa Sintética",
        "nacionalidade": "brasileiro(a)",
        "capacidade": "maior e capaz",
        "estado_civil": "solteiro",
        "uniao_estavel": False,
        "profissao": None,
        "cpf": "111",
        "endereco": None,
        "casamento": {},
        "empresa": {},
        "procuracao": {},
        "fontes": [],
        "origem": "MANUAL",
        "confirmado": False,
    }
    url = f"/api/analises/casos/{caso.id}/compra-venda"
    payload = {
        "partes": [parte],
        "imovel": {
            "matricula": "1-SINTETICA",
            "descricao_completa": "Descrição sintética",
            "confirmado": False,
        },
    }
    assert client.put(url, headers=auth_headers(admin), json=payload).status_code == 200
    status_url = f"/api/analises/casos/{caso.id}/status"
    assert (
        client.patch(
            status_url,
            headers=auth_headers(admin),
            json={"status": "PRONTO_PARA_ANALISE"},
        ).status_code
        == 409
    )
    payload["partes"][0]["confirmado"] = True
    payload["imovel"]["confirmado"] = True
    assert client.put(url, headers=auth_headers(admin), json=payload).status_code == 200
    resposta = client.patch(
        status_url, headers=auth_headers(admin), json={"status": "PRONTO_PARA_ANALISE"}
    )
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "PRONTO_PARA_ANALISE"


def test_snapshot_a1_inclui_estado_estruturado_sem_diagnostico(db, usuario_factory):
    admin = usuario_factory("admin-snapshot", role="ADMIN")
    caso = _caso(db, admin)
    caso.dados_ato = compra_venda.dados_vazios()
    caso.dados_ato["_diagnostico"] = {"hashes_blocos_processados": ["segredo-tecnico"]}
    db.commit()
    fatos, _ = _estado_atual(db, caso)
    estruturado = next(
        item for item in fatos if item["categoria"] == "COMPRA_VENDA_ESTRUTURADA"
    )
    assert "_diagnostico" not in estruturado["valor"]
    assert estruturado["valor"]["pendencias_de_conferencia"]


def test_alvara_e_procuracao_comparam_limites_sem_decidir_validade():
    representado_id, representante_id = uuid4(), uuid4()
    dados = compra_venda.dados_vazios()
    dados["negocio"].update({"valor_escritura": "R$ 150.000,00", "confirmado": True})
    dados["partes"] = [
        {
            "id": str(representado_id),
            "papel": "OUTORGANTE",
            "natureza": "FISICA",
            "participacao": "PRINCIPAL",
            "principal_id": None,
            "modo_qualificacao": "ALVARA_JUDICIAL",
            "nome_completo": "Representado Sintético",
            "nacionalidade": "brasileiro",
            "capacidade": None,
            "estado_civil": "solteiro",
            "profissao": "profissão teste",
            "cpf": "111",
            "endereco": "endereço teste",
            "uniao_estavel": False,
            "casamento": {},
            "empresa": {},
            "procuracao": {},
            "alvara": {
                "numero_processo": "0001",
                "juizo": "Juízo Teste",
                "data_decisao": "01/01/2026",
                "poderes": "alienar o imóvel",
                "valor_minimo": "R$ 200.000,00",
            },
            "fontes": [],
            "origem": "MANUAL",
            "confirmado": True,
        },
        {
            "id": str(representante_id),
            "papel": "OUTORGANTE",
            "natureza": "FISICA",
            "participacao": "REPRESENTANTE",
            "principal_id": str(representado_id),
            "modo_qualificacao": "INDIVIDUAL",
            "nome_completo": "Representante Sintético",
            "nacionalidade": "brasileiro",
            "capacidade": None,
            "estado_civil": "casado",
            "profissao": "profissão teste",
            "cpf": "222",
            "endereco": "endereço teste",
            "uniao_estavel": None,
            "casamento": {},
            "empresa": {},
            "procuracao": {},
            "alvara": {},
            "fontes": [],
            "origem": "MANUAL",
            "confirmado": True,
        },
    ]
    qualificacoes, _ = compra_venda.gerar_qualificacoes(dados)
    texto = next(
        item["texto"]
        for item in qualificacoes
        if item["parte_id"] == str(representado_id)
    )
    assert "representado(a) por Representante Sintético" in texto
    assert "processo nº 0001" in texto
    alertas = compra_venda.avaliar_limites_valor(dados)
    assert len(alertas) == 1
    assert "abaixo do mínimo" in alertas[0]
    assert "valid" not in alertas[0].casefold()
    dados["negocio"]["valor_escritura"] = "R$ 250.000,00"
    assert compra_venda.avaliar_limites_valor(dados) == []


def test_normalizacao_contextual_corrige_relacao_simples_de_alvara():
    partes = [
        {
            "papel": "OUTORGADO",
            "participacao": "PRINCIPAL",
            "nome_completo": "Representado Sintético",
            "modo_qualificacao": "PROCURACAO",
            "alvara": {"numero_processo": "0001"},
        },
        {
            "papel": "OUTORGADO",
            "participacao": "PROCURADOR",
            "nome_completo": "Representante Sintético",
            "principal_nome": None,
            "modo_qualificacao": "PROCURACAO",
            "alvara": {},
        },
    ]
    compra_venda._normalizar_representacao_contextual(
        partes, "ALVARA_JUDICIAL", "TRANSMITENTE"
    )
    assert partes[0]["papel"] == "OUTORGANTE"
    assert partes[0]["modo_qualificacao"] == "ALVARA_JUDICIAL"
    assert partes[1]["papel"] == "OUTORGANTE"
    assert partes[1]["participacao"] == "REPRESENTANTE"
    assert partes[1]["principal_nome"] == "Representado Sintético"


def test_normalizacao_contextual_recupera_alvara_classificado_como_procuracao():
    partes = [
        {
            "papel": "OUTORGADO",
            "participacao": "PRINCIPAL",
            "nome_completo": "Ana",
            "modo_qualificacao": "PROCURACAO",
            "alvara": {},
            "procuracao": {"poderes": "alienar", "valor_minimo": "R$ 200.000,00"},
        },
        {
            "papel": "OUTORGADO",
            "participacao": "PROCURADOR",
            "nome_completo": "Carlos",
            "modo_qualificacao": "PROCURACAO",
            "alvara": {},
            "procuracao": {},
        },
    ]
    compra_venda._normalizar_representacao_contextual(
        partes, "ALVARA_JUDICIAL", "TRANSMITENTE"
    )
    assert partes[0]["modo_qualificacao"] == "ALVARA_JUDICIAL"
    assert partes[0]["alvara"]["poderes"] == "alienar"
    assert partes[0]["alvara"]["valor_minimo"] == "R$ 200.000,00"
    assert not partes[0]["procuracao"].get("valor_minimo")
    assert partes[1]["participacao"] == "REPRESENTANTE"
