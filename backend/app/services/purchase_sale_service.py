"""A2 estruturado para Compra e Venda, sem decisão jurídica automática."""

import hashlib
import json
import logging
import re
import urllib.request
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from threading import Lock
from uuid import UUID, uuid4

from app.config import (
    A2_FACT_BLOCK_CHAR_LIMIT,
    A2_FACT_MAX_BLOCKS,
    OLLAMA_BASE_URL,
    OLLAMA_GENERATION_MODEL,
)
from app.database import SessionLocal
from app.models import Caso, CasoDocumento, CasoDocumentoPagina, utc_now
from app.prompts import (
    BASE_PROMPT_VERSION,
    COMPRA_VENDA_PROMPT_VERSION,
    build_compra_venda_prompt,
)
from app.services.case_fact_extraction_service import (
    _blocos,
    ollama_configurado_localmente,
)
from app.services.case_task_service import (
    concluir_tarefa,
    falhar_tarefa,
    iniciar_tarefa,
)

logger = logging.getLogger(__name__)
EXTRATOR_COMPRA_VENDA_VERSION = (
    f"a2.compra-venda.{COMPRA_VENDA_PROMPT_VERSION}+base.{BASE_PROMPT_VERSION}"
)
_reserva_lock = Lock()
_extracoes_ativas: set = set()


def reservar_extracao_compra_venda(caso_id) -> bool:
    with _reserva_lock:
        if caso_id in _extracoes_ativas:
            return False
        _extracoes_ativas.add(caso_id)
        return True


def liberar_extracao_compra_venda(caso_id) -> None:
    with _reserva_lock:
        _extracoes_ativas.discard(caso_id)


def dados_vazios() -> dict:
    return {
        "partes": [],
        "imovel": {
            "matricula": None,
            "logradouro": None,
            "numero": None,
            "bairro": None,
            "cidade": None,
            "descricao_completa": None,
            "descricao_utilizada": None,
            "averbacoes": [],
            "fontes": [],
            "origem": "MANUAL",
            "confirmado": False,
        },
        "negocio": {
            "valor_escritura": None,
            "forma_pagamento": None,
            "moeda": "BRL",
            "observacoes": None,
            "fontes": [],
            "confirmado": False,
        },
    }


def _normalizar(texto) -> str:
    return " ".join(str(texto or "").split()).casefold()


def _extrair_json(texto: str) -> dict:
    resposta = texto.strip()
    if resposta.startswith("```"):
        resposta = re.sub(r"^```(?:json)?\s*", "", resposta, flags=re.I)
        resposta = re.sub(r"\s*```$", "", resposta)
    inicio, fim = resposta.find("{"), resposta.rfind("}")
    if inicio < 0 or fim <= inicio:
        raise ValueError("Resposta sem objeto JSON.")
    dados = json.loads(resposta[inicio : fim + 1])
    if not isinstance(dados, dict):
        raise ValueError("Resposta estruturada fora do contrato.")
    return dados


def _gerar_dados(prompt: str) -> dict:
    requisicao = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=json.dumps(
            {
                "model": OLLAMA_GENERATION_MODEL,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "format": "json",
                "options": {"temperature": 0.0, "num_ctx": 12288, "num_predict": 2600},
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(requisicao, timeout=300) as resposta:
        retorno = json.loads(resposta.read().decode("utf-8"))
    texto = str(retorno.get("response") or "")
    if not texto:
        raise RuntimeError("O modelo local não retornou uma resposta.")
    return _extrair_json(texto)


def _fonte(documento: CasoDocumento, pagina: CasoDocumentoPagina, trecho: str) -> dict:
    return {
        "documento_id": str(documento.id),
        "pagina": pagina.pagina if pagina.pagina_confiavel else None,
        "localizacao": pagina.localizacao,
        "trecho": trecho[:2000],
    }


def _normalizar_representacao_contextual(
    partes: list[dict], tipo_documento: str | None, vinculo_ato: str | None
) -> None:
    """Organiza uma sugestão inequívoca; permanece pendente de conferência."""

    configuracoes = {
        "ALVARA_JUDICIAL": ("alvara", "ALVARA_JUDICIAL", "REPRESENTANTE"),
        "PROCURACAO": ("procuracao", "PROCURACAO", "PROCURADOR"),
    }
    configuracao = configuracoes.get(str(tipo_documento or "").upper())
    if configuracao is None or len(partes) < 2:
        return
    grupo, modo, participacao_representante = configuracao
    candidatos = [
        item
        for item in partes
        if isinstance(item.get(grupo), dict)
        and any(_valor_presente(valor) for valor in item[grupo].values())
    ]
    principais = [
        item for item in candidatos if item.get("participacao") == "PRINCIPAL"
    ]
    if len(principais) == 1:
        principal = principais[0]
    elif len(candidatos) == 1:
        principal = candidatos[0]
    else:
        # Modelos menores podem classificar corretamente a pessoa principal,
        # mas colocar os dados do instrumento no grupo errado. Em documento
        # inequivocamente classificado, a participação PRINCIPAL é a referência.
        principais_contextuais = [
            item for item in partes if item.get("participacao") == "PRINCIPAL"
        ]
        principal = (
            principais_contextuais[0] if len(principais_contextuais) == 1 else None
        )
    if principal is None:
        return
    grupo_incorreto = "procuracao" if grupo == "alvara" else "alvara"
    dados_corretos = (
        principal.get(grupo) if isinstance(principal.get(grupo), dict) else {}
    )
    dados_incorretos = (
        principal.get(grupo_incorreto)
        if isinstance(principal.get(grupo_incorreto), dict)
        else {}
    )
    # Somente campos comuns aos dois instrumentos podem migrar automaticamente.
    # Dados específicos continuam vazios e destacados para conferência humana.
    for campo in ("poderes", "valor_minimo", "valor_maximo"):
        if not _valor_presente(dados_corretos.get(campo)) and _valor_presente(
            dados_incorretos.get(campo)
        ):
            dados_corretos[campo] = dados_incorretos[campo]
            dados_incorretos[campo] = None
    principal[grupo] = dados_corretos
    principal[grupo_incorreto] = dados_incorretos
    principal["participacao"] = "PRINCIPAL"
    principal["modo_qualificacao"] = modo
    papel_contextual = {
        "TRANSMITENTE": "OUTORGANTE",
        "ADQUIRENTE": "OUTORGADO",
    }.get(str(vinculo_ato or "").upper())
    if papel_contextual:
        principal["papel"] = papel_contextual
    outros = [item for item in partes if item is not principal]
    if len(outros) != 1:
        return
    representante = outros[0]
    representante["participacao"] = participacao_representante
    representante["principal_nome"] = principal.get("nome_completo")
    if papel_contextual:
        representante["papel"] = papel_contextual
    for grupo_origem in (grupo, grupo_incorreto):
        dados_origem = (
            representante.get(grupo_origem)
            if isinstance(representante.get(grupo_origem), dict)
            else {}
        )
        for campo in ("poderes", "valor_minimo", "valor_maximo"):
            if not _valor_presente(principal[grupo].get(campo)) and _valor_presente(
                dados_origem.get(campo)
            ):
                principal[grupo][campo] = dados_origem[campo]
            dados_origem[campo] = None
        representante[grupo_origem] = dados_origem
    if (
        isinstance(representante.get(grupo), dict)
        and any(_valor_presente(valor) for valor in representante[grupo].values())
        and not any(
            _valor_presente(valor) for valor in (principal.get(grupo) or {}).values()
        )
    ):
        principal[grupo] = representante[grupo]
    representante[grupo] = {}


def _validar_resposta(
    dados: dict, texto: str, documento: CasoDocumento, pagina: CasoDocumentoPagina
) -> tuple[dict, int]:
    """Descarta qualquer item cuja evidência não seja literal no bloco recebido."""

    validado = {"partes": [], "imovel": {}, "negocio": {}}
    descartados = 0
    bloco = _normalizar(texto)
    partes = dados.get("partes") if isinstance(dados.get("partes"), list) else []
    for item in partes[:50]:
        if not isinstance(item, dict):
            descartados += 1
            continue
        trecho = str(item.get("trecho_fonte") or "").strip()
        if not trecho or _normalizar(trecho) not in bloco:
            descartados += 1
            continue
        copia = {
            chave: valor for chave, valor in item.items() if chave != "trecho_fonte"
        }
        copia["fontes"] = [_fonte(documento, pagina, trecho)]
        validado["partes"].append(copia)

    _normalizar_representacao_contextual(
        validado["partes"], documento.tipo_documento, documento.vinculo_ato
    )

    imovel = dados.get("imovel") if isinstance(dados.get("imovel"), dict) else {}
    trecho_imovel = str(imovel.get("trecho_fonte") or "").strip()
    if trecho_imovel and _normalizar(trecho_imovel) in bloco:
        validado["imovel"] = {
            chave: valor
            for chave, valor in imovel.items()
            if chave not in {"trecho_fonte", "averbacoes"}
        }
        validado["imovel"]["fontes"] = [_fonte(documento, pagina, trecho_imovel)]
    elif any(
        imovel.get(chave) for chave in ("matricula", "logradouro", "descricao_completa")
    ):
        descartados += 1

    validado["imovel"]["averbacoes"] = []
    averbacoes = (
        imovel.get("averbacoes") if isinstance(imovel.get("averbacoes"), list) else []
    )
    for indice, item in enumerate(averbacoes[:500], start=1):
        if not isinstance(item, dict):
            descartados += 1
            continue
        trecho = str(item.get("trecho_fonte") or "").strip()
        rotulo = str(item.get("rotulo") or "").strip()[:50]
        resumo = str(item.get("resumo") or "").strip()[:2000]
        if not trecho or _normalizar(trecho) not in bloco or not rotulo or not resumo:
            descartados += 1
            continue
        validado["imovel"]["averbacoes"].append(
            {
                "ordem": indice,
                "rotulo": rotulo,
                "resumo": resumo,
                "fonte": _fonte(documento, pagina, trecho),
            }
        )
    negocio = dados.get("negocio") if isinstance(dados.get("negocio"), dict) else {}
    trecho_negocio = str(negocio.get("trecho_fonte") or "").strip()
    if trecho_negocio and _normalizar(trecho_negocio) in bloco:
        validado["negocio"] = {
            chave: valor for chave, valor in negocio.items() if chave != "trecho_fonte"
        }
        validado["negocio"]["fontes"] = [_fonte(documento, pagina, trecho_negocio)]
    elif any(
        negocio.get(chave)
        for chave in ("valor_escritura", "forma_pagamento", "observacoes")
    ):
        descartados += 1
    return validado, descartados


def _valor_presente(valor) -> bool:
    return valor not in (None, "", [], {})


def _mesclar_campos(destino: dict, origem: dict, campos: tuple[str, ...]) -> None:
    for campo in campos:
        if not _valor_presente(destino.get(campo)) and _valor_presente(
            origem.get(campo)
        ):
            destino[campo] = origem[campo]


def _chave_parte(parte: dict) -> str:
    cpf = re.sub(r"\D", "", str(parte.get("cpf") or ""))
    if cpf:
        return f"cpf:{cpf}"
    return f"nome:{_normalizar(parte.get('nome_completo'))}"


def _nova_parte(sugestao: dict) -> dict:
    papel = str(sugestao.get("papel") or "OUTORGADO").upper()
    papel = {"VENDEDOR": "OUTORGANTE", "COMPRADOR": "OUTORGADO"}.get(papel, papel)
    if papel not in {"OUTORGANTE", "OUTORGADO"}:
        papel = "OUTORGADO"
    participacao = str(sugestao.get("participacao") or "PRINCIPAL").upper()
    if participacao not in {
        "PRINCIPAL",
        "CONJUGE",
        "ANUENTE",
        "REPRESENTANTE",
        "PROCURADOR",
    }:
        participacao = "PRINCIPAL"
    natureza = str(sugestao.get("natureza") or "FISICA").upper()
    if natureza not in {"FISICA", "JURIDICA"}:
        natureza = "FISICA"
    return {
        "id": str(uuid4()),
        "papel": papel,
        "natureza": natureza,
        "participacao": participacao,
        "principal_id": None,
        "modo_qualificacao": (
            "EMPRESA_REPRESENTADA" if natureza == "JURIDICA" else "INDIVIDUAL"
        ),
        "nome_completo": sugestao.get("nome_completo"),
        "nacionalidade": sugestao.get("nacionalidade") or "brasileiro(a)",
        "capacidade": sugestao.get("capacidade"),
        "estado_civil": sugestao.get("estado_civil"),
        "uniao_estavel": sugestao.get("uniao_estavel"),
        "profissao": sugestao.get("profissao"),
        "cpf": sugestao.get("cpf"),
        "endereco": sugestao.get("endereco"),
        "casamento": (
            sugestao.get("casamento")
            if isinstance(sugestao.get("casamento"), dict)
            else {}
        ),
        "empresa": (
            sugestao.get("empresa") if isinstance(sugestao.get("empresa"), dict) else {}
        ),
        "procuracao": (
            sugestao.get("procuracao")
            if isinstance(sugestao.get("procuracao"), dict)
            else {}
        ),
        "alvara": (
            sugestao.get("alvara") if isinstance(sugestao.get("alvara"), dict) else {}
        ),
        "fontes": sugestao.get("fontes") or [],
        "origem": "IA",
        "confirmado": False,
    }


def mesclar_sugestoes(atual: dict | None, sugestoes: dict) -> dict:
    """Preenche apenas lacunas; valores humanos/confirmados nunca são substituídos."""

    resultado = deepcopy(atual or dados_vazios())
    resultado.setdefault("partes", [])
    resultado.setdefault("imovel", dados_vazios()["imovel"])
    resultado.setdefault("negocio", dados_vazios()["negocio"])
    for parte_existente in resultado["partes"]:
        parte_existente["papel"] = {
            "VENDEDOR": "OUTORGANTE",
            "COMPRADOR": "OUTORGADO",
        }.get(parte_existente.get("papel"), parte_existente.get("papel"))
    por_chave = {
        _chave_parte(item): item
        for item in resultado["partes"]
        if _normalizar(item.get("nome_completo")) or item.get("cpf")
    }
    principais_por_nome = {
        _normalizar(item.get("nome_completo")): item.get("id")
        for item in resultado["partes"]
        if item.get("participacao") == "PRINCIPAL"
    }
    for sugestao in sugestoes.get("partes", []):
        chave = _chave_parte(sugestao)
        parte = por_chave.get(chave)
        if parte is None:
            parte = _nova_parte(sugestao)
            resultado["partes"].append(parte)
            por_chave[chave] = parte
        elif not parte.get("confirmado"):
            _mesclar_campos(
                parte,
                sugestao,
                (
                    "nome_completo",
                    "nacionalidade",
                    "capacidade",
                    "estado_civil",
                    "uniao_estavel",
                    "profissao",
                    "cpf",
                    "endereco",
                ),
            )
            for grupo in ("casamento", "empresa", "procuracao", "alvara"):
                parte.setdefault(grupo, {})
                if isinstance(sugestao.get(grupo), dict):
                    _mesclar_campos(
                        parte[grupo], sugestao[grupo], tuple(sugestao[grupo].keys())
                    )
            fontes = parte.setdefault("fontes", [])
            for fonte in sugestao.get("fontes", []):
                if fonte not in fontes:
                    fontes.append(fonte)
        principal_nome = _normalizar(sugestao.get("principal_nome"))
        if not parte.get("principal_id") and principal_nome in principais_por_nome:
            parte["principal_id"] = principais_por_nome[principal_nome]
        if parte.get("participacao") == "PRINCIPAL" and parte.get("nome_completo"):
            principais_por_nome[_normalizar(parte["nome_completo"])] = parte["id"]

    imovel = resultado["imovel"]
    sugestao_imovel = sugestoes.get("imovel") or {}
    if not imovel.get("confirmado"):
        _mesclar_campos(
            imovel,
            sugestao_imovel,
            (
                "matricula",
                "logradouro",
                "numero",
                "bairro",
                "cidade",
                "descricao_completa",
            ),
        )
        fontes = imovel.setdefault("fontes", [])
        for fonte in sugestao_imovel.get("fontes", []):
            if fonte not in fontes:
                fontes.append(fonte)
        existentes = {
            (_normalizar(item.get("rotulo")), _normalizar(item.get("resumo")))
            for item in imovel.setdefault("averbacoes", [])
        }
        for item in sugestao_imovel.get("averbacoes", []):
            chave = (_normalizar(item.get("rotulo")), _normalizar(item.get("resumo")))
            if chave not in existentes:
                imovel["averbacoes"].append(item)
                existentes.add(chave)
    atualizar_descricao_imovel(imovel)
    negocio = resultado["negocio"]
    sugestao_negocio = sugestoes.get("negocio") or {}
    if not negocio.get("confirmado"):
        _mesclar_campos(
            negocio,
            sugestao_negocio,
            ("valor_escritura", "forma_pagamento", "moeda", "observacoes"),
        )
        fontes = negocio.setdefault("fontes", [])
        for fonte in sugestao_negocio.get("fontes", []):
            if fonte not in fontes:
                fontes.append(fonte)
    return resultado


def atualizar_descricao_imovel(imovel: dict) -> None:
    endereco = [
        imovel.get(campo) for campo in ("logradouro", "numero", "bairro", "cidade")
    ]
    if all(_valor_presente(valor) for valor in endereco):
        imovel["descricao_utilizada"] = (
            f"{endereco[0]}, nº {endereco[1]}, bairro {endereco[2]}, {endereco[3]}"
        )
    else:
        imovel["descricao_utilizada"] = imovel.get("descricao_completa")


def _texto(valor, marcador: str) -> str:
    return str(valor).strip() if _valor_presente(valor) else f"[{marcador}]"


def _qualificacao_fisica(parte: dict, *, incluir_capacidade: bool = True) -> str:
    capacidade = (
        f", {_texto(parte.get('capacidade'), 'CAPACIDADE')}"
        if incluir_capacidade
        else ""
    )
    return (
        f"{_texto(parte.get('nome_completo'), 'NOME COMPLETO')}, "
        f"{_texto(parte.get('nacionalidade'), 'NACIONALIDADE')}{capacidade}, "
        f"{_texto(parte.get('estado_civil'), 'ESTADO CIVIL')}, "
        f"{_texto(parte.get('profissao'), 'PROFISSÃO')}, inscrito(a) no CPF sob nº "
        f"{_texto(parte.get('cpf'), 'CPF')}, residente e domiciliado(a) em "
        f"{_texto(parte.get('endereco'), 'ENDEREÇO')}"
    )


def _pendencias_fisica(parte: dict, *, capacidade: bool = True) -> list[str]:
    campos = [
        ("nome_completo", "nome completo"),
        ("cpf", "CPF"),
        ("estado_civil", "estado civil"),
        ("profissao", "profissão"),
        ("endereco", "endereço"),
    ]
    if capacidade:
        campos.append(("capacidade", "capacidade"))
    return [rotulo for campo, rotulo in campos if not _valor_presente(parte.get(campo))]


def gerar_qualificacoes(dados: dict | None) -> tuple[list[dict], list[str]]:
    dados = dados or dados_vazios()
    partes = dados.get("partes") or []
    por_id = {str(item.get("id")): item for item in partes}
    resultados = []
    pendencias_gerais = []
    for parte in partes:
        pendencias = []
        nome = _texto(parte.get("nome_completo"), "NOME COMPLETO")
        if parte.get("natureza") == "JURIDICA":
            empresa = parte.get("empresa") or {}
            representante = next(
                (
                    item
                    for item in partes
                    if str(item.get("principal_id")) == str(parte.get("id"))
                    and item.get("participacao") == "REPRESENTANTE"
                ),
                None,
            )
            texto = (
                f"{nome}, inscrita no CNPJ sob nº {_texto(empresa.get('cnpj'), 'CNPJ')}, "
                f"NIRE {_texto(empresa.get('nire'), 'NIRE')}, com endereço em {_texto(empresa.get('endereco'), 'ENDEREÇO')}, "
                f"neste ato representada por {_qualificacao_fisica(representante or {}, incluir_capacidade=False)}, "
                f"conforme poderes conferidos pela cláusula "
                f"{_texto(empresa.get('clausula_poderes'), 'CLÁUSULA')}: "
                f"{_texto(empresa.get('descricao_poderes'), 'DESCRIÇÃO DOS PODERES')}"
            )
            if representante is None:
                pendencias.append("representante da empresa")
            for campo, rotulo in (
                ("cnpj", "CNPJ"),
                ("nire", "NIRE"),
                ("endereco", "endereço da empresa"),
                ("clausula_poderes", "cláusula de poderes"),
                ("descricao_poderes", "poderes de representação"),
            ):
                if not _valor_presente(empresa.get(campo)):
                    pendencias.append(rotulo)
        else:
            omitir_capacidade = parte.get("participacao") in {
                "REPRESENTANTE",
                "PROCURADOR",
            }
            texto = _qualificacao_fisica(
                parte, incluir_capacidade=not omitir_capacidade
            )
            pendencias.extend(
                _pendencias_fisica(parte, capacidade=not omitir_capacidade)
            )
            modo = parte.get("modo_qualificacao")
            principal = por_id.get(str(parte.get("principal_id")))
            casamento = (principal or parte).get("casamento") or {}
            if modo == "UNIAO_ESTAVEL":
                parceiro = (
                    principal
                    if principal and principal is not parte
                    else next(
                        (
                            item
                            for item in partes
                            if str(item.get("principal_id")) == str(parte.get("id"))
                            and item.get("participacao") == "CONJUGE"
                        ),
                        None,
                    )
                )
                texto += f", declara que vive em união estável com {_qualificacao_fisica(parceiro or {})}"
                if parceiro is None:
                    pendencias.append("companheiro(a) da união estável")
            elif modo == "INDIVIDUAL" and parte.get("uniao_estavel") is False:
                texto += ", o(a) qual declara que não convive em união estável"
            elif modo in {
                "CASAL_AMBOS_ASSINAM",
                "CASAL_COM_ANUENTE",
                "CASADO_APENAS_UM",
            }:
                conjuge = next(
                    (
                        item
                        for item in partes
                        if str(item.get("principal_id")) == str(parte.get("id"))
                        and item.get("participacao") in {"CONJUGE", "ANUENTE"}
                    ),
                    None,
                )
                if conjuge is None:
                    pendencias.append("cônjuge relacionado")
                if modo == "CASAL_COM_ANUENTE":
                    apresentacao = f"e seu(ua) cônjuge, na qualidade de interveniente anuente, {_qualificacao_fisica(conjuge or {})}"
                elif modo == "CASADO_APENAS_UM":
                    apresentacao = f"casado(a) com {_qualificacao_fisica(conjuge or {}, incluir_capacidade=False)}"
                else:
                    apresentacao = (
                        f"e seu(ua) cônjuge {_qualificacao_fisica(conjuge or {})}"
                    )
                texto += (
                    f", {apresentacao}, "
                    f"sendo o matrimônio celebrado/registrado em {_texto(casamento.get('data_registro'), 'DATA DO CASAMENTO')}, "
                    f"pelo regime {_texto(casamento.get('regime_bens'), 'REGIME DE BENS')}, conforme certidão emitida em "
                    f"{_texto(casamento.get('data_certidao'), 'DATA DA CERTIDÃO')}, selo digital "
                    f"{_texto(casamento.get('selo_digital'), 'SELO DIGITAL')}"
                )
                for campo, rotulo in (
                    ("data_registro", "data do casamento"),
                    ("regime_bens", "regime de bens"),
                    ("data_certidao", "data da certidão de casamento"),
                    ("selo_digital", "selo da certidão de casamento"),
                ):
                    if not _valor_presente(casamento.get(campo)):
                        pendencias.append(rotulo)
            if modo == "PROCURACAO":
                procuracao = parte.get("procuracao") or {}
                procurador = next(
                    (
                        item
                        for item in partes
                        if str(item.get("principal_id")) == str(parte.get("id"))
                        and item.get("participacao") == "PROCURADOR"
                    ),
                    None,
                )
                representacao = (
                    f", neste ato representado(a) por "
                    f"{_qualificacao_fisica(procurador, incluir_capacidade=False)}"
                    if procurador
                    else ""
                )
                texto += (
                    f"{representacao}, conforme procuração lavrada em {_texto(procuracao.get('lavrada_em'), 'DATA')}, "
                    f"livro {_texto(procuracao.get('livro'), 'LIVRO')}, folhas {_texto(procuracao.get('folhas'), 'FOLHAS')}, "
                    f"do {_texto(procuracao.get('tabelionato'), 'TABELIONATO')} de {_texto(procuracao.get('cidade_comarca'), 'CIDADE/COMARCA')}, "
                    f"certidão emitida em {_texto(procuracao.get('certidao_emitida_em'), 'DATA DA CERTIDÃO')}, "
                    f"selo digital {_texto(procuracao.get('selo_digital'), 'SELO DIGITAL')}, com poderes: "
                    f"{_texto(procuracao.get('poderes'), 'PODERES')}"
                )
                if parte.get("participacao") == "PRINCIPAL" and procurador is None:
                    pendencias.append("procurador relacionado")
                for campo, rotulo in (
                    ("lavrada_em", "data da procuração"),
                    ("livro", "livro da procuração"),
                    ("folhas", "folhas da procuração"),
                    ("tabelionato", "tabelionato da procuração"),
                    ("cidade_comarca", "cidade/comarca da procuração"),
                    ("certidao_emitida_em", "emissão da certidão da procuração"),
                    ("selo_digital", "selo da procuração"),
                    ("poderes", "poderes da procuração"),
                ):
                    if not _valor_presente(procuracao.get(campo)):
                        pendencias.append(rotulo)
            if modo == "ALVARA_JUDICIAL":
                alvara = parte.get("alvara") or {}
                representante = next(
                    (
                        item
                        for item in partes
                        if str(item.get("principal_id")) == str(parte.get("id"))
                        and item.get("participacao") == "REPRESENTANTE"
                    ),
                    None,
                )
                texto += (
                    f", neste ato representado(a) por "
                    f"{_qualificacao_fisica(representante or {}, incluir_capacidade=False)}, "
                    f"nos termos do alvará judicial do processo nº "
                    f"{_texto(alvara.get('numero_processo'), 'PROCESSO')}, expedido pelo "
                    f"{_texto(alvara.get('juizo'), 'JUÍZO')}, com decisão em "
                    f"{_texto(alvara.get('data_decisao'), 'DATA DA DECISÃO')}, poderes: "
                    f"{_texto(alvara.get('poderes'), 'PODERES')}"
                )
                if representante is None:
                    pendencias.append("representante judicial relacionado")
                for campo, rotulo in (
                    ("numero_processo", "processo do alvará"),
                    ("juizo", "juízo do alvará"),
                    ("data_decisao", "data da decisão"),
                    ("poderes", "poderes do alvará"),
                ):
                    if not _valor_presente(alvara.get(campo)):
                        pendencias.append(rotulo)
        if not parte.get("confirmado"):
            pendencias.append("conferência humana da parte")
        resultados.append(
            {
                "parte_id": str(parte.get("id")),
                "texto": texto + ";",
                "pendencias": sorted(set(pendencias)),
            }
        )
        pendencias_gerais.extend(f"{nome}: {item}" for item in pendencias)

    imovel = dados.get("imovel") or {}
    atualizar_descricao_imovel(imovel)
    if not _valor_presente(imovel.get("matricula")):
        pendencias_gerais.append("Imóvel: matrícula")
    if not _valor_presente(imovel.get("descricao_utilizada")):
        pendencias_gerais.append("Imóvel: descrição")
    if not imovel.get("confirmado"):
        pendencias_gerais.append("Imóvel: conferência humana")
    return resultados, sorted(set(pendencias_gerais))


def _valor_decimal(valor) -> Decimal | None:
    texto = re.sub(r"[^0-9,.-]", "", str(valor or ""))
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def avaliar_limites_valor(dados: dict | None) -> list[str]:
    """Sinaliza divergências objetivas; não conclui validade nem autoriza o ato."""

    dados = dados or dados_vazios()
    valor_escritura = _valor_decimal(
        (dados.get("negocio") or {}).get("valor_escritura")
    )
    alertas = []
    for parte in dados.get("partes") or []:
        modo = parte.get("modo_qualificacao")
        if modo not in {"PROCURACAO", "ALVARA_JUDICIAL"}:
            continue
        documento = (
            parte.get("procuracao") if modo == "PROCURACAO" else parte.get("alvara")
        )
        documento = documento or {}
        minimo = _valor_decimal(documento.get("valor_minimo"))
        maximo = _valor_decimal(documento.get("valor_maximo"))
        identificacao = _texto(parte.get("nome_completo"), "PARTE SEM NOME")
        origem = "procuração" if modo == "PROCURACAO" else "alvará judicial"
        if (minimo is not None or maximo is not None) and valor_escritura is None:
            alertas.append(
                f"{identificacao}: informe o valor da escritura para conferir os limites da {origem}."
            )
            continue
        if (
            valor_escritura is not None
            and minimo is not None
            and valor_escritura < minimo
        ):
            alertas.append(
                f"{identificacao}: o valor da escritura está abaixo do mínimo indicado na {origem}."
            )
        if (
            valor_escritura is not None
            and maximo is not None
            and valor_escritura > maximo
        ):
            alertas.append(
                f"{identificacao}: o valor da escritura está acima do máximo indicado na {origem}."
            )
    return sorted(set(alertas))


def processar_compra_venda(caso_id, tarefa_id: UUID | None = None) -> None:
    db = SessionLocal()
    try:
        iniciar_tarefa(tarefa_id)
        caso = db.get(Caso, caso_id)
        if caso is None or caso.tipo_ato != "COMPRA_VENDA":
            falhar_tarefa(tarefa_id, "Caso não encontrado ou tipo de ato inválido.")
            return
        if not ollama_configurado_localmente():
            raise RuntimeError("Ollama não local recusado para documento privado.")
        documentos = (
            db.query(CasoDocumento)
            .filter(
                CasoDocumento.caso_id == caso.id,
                CasoDocumento.status == "PRONTO",
                CasoDocumento.status_seguranca == "LIBERADO",
                CasoDocumento.situacao_extracao == "PROCESSADO_COMPLETO",
            )
            .order_by(CasoDocumento.created_at.asc(), CasoDocumento.id.asc())
            .all()
        )
        atual = deepcopy(caso.dados_ato or dados_vazios())
        diagnostico = (
            atual.get("_diagnostico")
            if isinstance(atual.get("_diagnostico"), dict)
            else {}
        )
        hashes = (
            set(diagnostico.get("hashes_blocos_processados") or [])
            if diagnostico.get("versao") == EXTRATOR_COMPRA_VENDA_VERSION
            else set()
        )
        blocos = []
        for documento in documentos:
            paginas = (
                db.query(CasoDocumentoPagina)
                .filter(CasoDocumentoPagina.caso_documento_id == documento.id)
                .order_by(CasoDocumentoPagina.pagina.asc())
                .all()
            )
            for pagina in paginas:
                for numero, texto in enumerate(
                    _blocos(pagina.conteudo or "", max(A2_FACT_BLOCK_CHAR_LIMIT, 1000)),
                    start=1,
                ):
                    hash_bloco = hashlib.sha256(
                        f"{documento.id}|{pagina.id}|{numero}|{texto}".encode("utf-8")
                    ).hexdigest()
                    blocos.append((documento, pagina, texto, hash_bloco))
        pendentes = [item for item in blocos if item[3] not in hashes]
        descartados = 0
        processados = 0
        for documento, pagina, texto, hash_bloco in pendentes[
            : max(A2_FACT_MAX_BLOCKS, 1)
        ]:
            resposta = _gerar_dados(
                build_compra_venda_prompt(
                    texto=texto,
                    tipo_documento=documento.tipo_documento,
                    vinculo_ato=documento.vinculo_ato,
                    localizacao=pagina.localizacao or f"Bloco {pagina.pagina}",
                )
            )
            validado, total_descartado = _validar_resposta(
                resposta, texto, documento, pagina
            )
            atual = mesclar_sugestoes(atual, validado)
            descartados += total_descartado
            processados += 1
            hashes.add(hash_bloco)
        parcial = len(hashes) < len(blocos)
        atual["_diagnostico"] = {
            "versao": EXTRATOR_COMPRA_VENDA_VERSION,
            "modelo": OLLAMA_GENERATION_MODEL,
            "total_blocos": len(blocos),
            "blocos_processados": len(hashes),
            "blocos_processados_nesta_execucao": processados,
            "itens_descartados_sem_evidencia_literal": descartados,
            "hashes_blocos_processados": sorted(hashes),
        }
        caso.dados_ato = atual
        caso.status_dados_ato = "PRONTO_PARCIAL" if parcial else "PRONTO"
        caso.erro_dados_ato = None
        caso.dados_ato_atualizados_em = utc_now()
        if caso.status == "EM_PREPARACAO":
            caso.status = "AGUARDANDO_CONFERENCIA"
        db.commit()
        concluir_tarefa(tarefa_id)
    except Exception as erro:
        db.rollback()
        logger.error(
            "Falha na extração estruturada do caso %s (tipo=%s).",
            caso_id,
            type(erro).__name__,
        )
        caso = db.get(Caso, caso_id)
        if caso is not None:
            caso.status_dados_ato = "ERRO"
            caso.erro_dados_ato = "Não foi possível extrair os dados de Compra e Venda com a IA local. Verifique o Ollama e tente novamente."
            caso.dados_ato_atualizados_em = utc_now()
            db.commit()
        falhar_tarefa(tarefa_id, "Não foi possível extrair os dados do caso.")
    finally:
        db.close()
        liberar_extracao_compra_venda(caso_id)
