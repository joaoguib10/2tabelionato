import json
import logging
import math
import re
import unicodedata
import uuid
from datetime import date, datetime, time, timezone
from time import perf_counter
from zoneinfo import ZoneInfo

from app.auth import get_current_user
from app.dependencies import get_db
from app.models import (
    ConsultaFonte,
    ConsultaHistorico,
    ConsultaRevisao,
    DocumentoPagina,
    Usuario,
    utc_now,
)
from app.permissions import require_roles
from app.schemas import (
    ConsultaFeedbackRequest,
    ConsultaFonteHistoricoResponse,
    ConsultaHistoricoListResponse,
    ConsultaHistoricoResponse,
    ConsultaRequest,
    ConsultaResponse,
    ConsultaRevisaoHistoricoResponse,
)
from app.services.consultation_knowledge_service import (
    buscar_entendimentos_publicados,
    buscar_respostas_revisadas_admin,
)
from app.services.ollama_service import gerar_resposta, obter_metadados_consulta
from app.services.semantic_search_service import buscar_chunks_semelhantes
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/consultar", tags=["Consulta"])
logger = logging.getLogger(__name__)
PADRAO_FONTE = re.compile(r"\[(FONTE-[^\]]+)\]")
PADRAO_FUNDAMENTACAO = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?:\*\*)?fundamentação(?:\*\*)?\s*:?[^\n]*$"
)
PADRAO_ITEM_CHECKLIST = re.compile(
    r"^\s*(?:[-*•–—]\s+|\d{1,3}\s*[.)]\s+|[a-zA-Z]\s*[.)]\s+|"
    r"[IVXLCDM]+\s*[-–—.)]\s+)(.+)$",
    re.IGNORECASE,
)
PADRAO_CABECALHO_SECAO_CHECKLIST = re.compile(
    r"^(?:pessoas?\s+juridicas?|vendedor(?:es|a|as)?|comprador(?:es|a|as)?|"
    r"outorgante(?:s)?|outorgado(?:s)?|alienante(?:s)?|adquirente(?:s)?|"
    r"doador(?:es|a|as)?|donatario(?:s)?|do\s+imovel|informar|"
    r"documentos?\s+necessarios)\b"
)
MAX_HISTORICO_PROMPT = 1_200
MAX_CONSULTA_RECUPERACAO = 1_800
# O Ollama local usa um contexto pequeno por causa da RAM disponível. Evita
# passar mais texto do que o modelo consegue manter junto das instruções.
MAX_CONTEXTO = 20_000
RESPOSTA_BASE_INSUFICIENTE = (
    "A base foi consultada, mas os trechos recuperados não sustentaram evidência "
    "direta suficiente para validar a resposta gerada. Isso não significa que o "
    "documento esteja ausente: a resposta foi limitada para não atribuir à fonte "
    "algo que ela não confirma. Delimite o ponto ou encaminhe a pergunta para revisão."
)
RESPOSTA_FORMATO_INVALIDO = (
    "A resposta automática não veio em português claro e direto, então foi "
    "descartada. Reformule a pergunta ou encaminhe-a para Revisões; nenhuma "
    "fonte foi atribuída a essa resposta."
)
PALAVRAS_INGLES = {
    "about",
    "and",
    "are",
    "because",
    "be",
    "been",
    "by",
    "can",
    "cannot",
    "content",
    "document",
    "each",
    "first",
    "for",
    "from",
    "go",
    "if",
    "in",
    "is",
    "it",
    "let",
    "need",
    "not",
    "of",
    "on",
    "only",
    "or",
    "provided",
    "second",
    "should",
    "source",
    "starting",
    "talks",
    "that",
    "the",
    "their",
    "they",
    "third",
    "this",
    "through",
    "to",
    "understand",
    "user",
    "want",
    "with",
    "would",
}
PALAVRAS_PORTUGUES = {
    "apenas",
    "artigo",
    "ata",
    "base",
    "como",
    "com",
    "conforme",
    "e",
    "da",
    "das",
    "de",
    "deve",
    "devem",
    "do",
    "dos",
    "documento",
    "documentos",
    "em",
    "essa",
    "esse",
    "esta",
    "exige",
    "ha",
    "na",
    "nao",
    "no",
    "normas",
    "o",
    "os",
    "ou",
    "para",
    "pode",
    "podem",
    "por",
    "precisa",
    "que",
    "sao",
    "se",
    "sem",
    "sim",
    "um",
    "uma",
}
PADRAO_RACIOCINIO_EXPOSTO = re.compile(
    r"(?i)\b(?:okay\s*,?\s+let'?s\s+(?:tackle|analyze|go through)|"
    r"the user (?:provided|asked|wants)|first,? i need to|"
    r"let me go through|starting with the (?:first|second|third) source|"
    r"(?:first|second|third) source \(id|"
    r"vou analisar as fontes|primeiro,? preciso entender)\b"
)
FUSO_LOCAL = ZoneInfo("America/Sao_Paulo")


def _normalizar(texto: str) -> str:
    decompleto = unicodedata.normalize("NFD", texto.casefold())
    return "".join(
        caractere for caractere in decompleto if unicodedata.category(caractere) != "Mn"
    )


def _termos_relevantes(texto: str) -> set[str]:
    ignorados = {
        "para",
        "como",
        "uma",
        "das",
        "dos",
        "que",
        "com",
        "sem",
        "por",
        "esta",
        "este",
        "isso",
        "ser",
        "sao",
        "foi",
        "deve",
        "pode",
    }
    return {
        termo
        for termo in re.findall(r"\b[\w]+\b", _normalizar(texto))
        if len(termo) >= 4 and termo not in ignorados
    }


def _resposta_direta_em_portugues(texto: str) -> bool:
    """Bloqueia raciocínio exposto e respostas majoritariamente em inglês."""
    texto_sem_fontes = PADRAO_FONTE.sub(" ", texto)
    if PADRAO_RACIOCINIO_EXPOSTO.search(texto_sem_fontes):
        return False

    tokens = re.findall(r"\b[a-z]+\b", _normalizar(texto_sem_fontes))
    if len(tokens) < 3:
        return True

    ingles = sum(token in PALAVRAS_INGLES for token in tokens)
    portugues = sum(token in PALAVRAS_PORTUGUES for token in tokens)
    return not (ingles >= 2 and ingles > portugues and ingles / len(tokens) >= 0.12)


def _possui_negacao(texto: str) -> bool:
    marcadores = {
        "nao",
        "nunca",
        "jamais",
        "sem",
        "dispensa",
        "dispensada",
        "dispensado",
        "desnecessaria",
        "desnecessario",
        "inexigivel",
        "proibida",
        "proibido",
        "vedada",
        "vedado",
    }
    palavras = set(re.findall(r"\b[\w]+\b", _normalizar(texto)))
    return bool(palavras & marcadores)


def _negacao_contraditoria(afirmacao: str, conteudo_fonte: str) -> bool:
    """Compara a polaridade com a parte da fonte lexicalmente relacionada.

    Um chunk pode reunir várias regras positivas e negativas. Comparar a
    afirmação com o chunk inteiro cria falsos negativos quando uma negação
    aparece em outro artigo, parágrafo ou inciso.
    """
    termos = _termos_relevantes(afirmacao)
    if not termos:
        return False

    unidades = [
        unidade
        for unidade in _separar_unidades(conteudo_fonte)
        if _termos_relevantes(unidade)
    ]
    pontuacoes = [len(termos & _termos_relevantes(unidade)) for unidade in unidades]
    melhor_pontuacao = max(pontuacoes, default=0)
    minimo = max(2, math.ceil(len(termos) * 0.35))
    if melhor_pontuacao < minimo:
        return False

    unidades_correspondentes = [
        unidade
        for unidade, pontuacao in zip(unidades, pontuacoes, strict=True)
        if pontuacao == melhor_pontuacao
    ]
    polaridade_afirmacao = _possui_negacao(afirmacao)
    return any(
        _possui_negacao(unidade) != polaridade_afirmacao
        for unidade in unidades_correspondentes
    )


def _afirmacao_respeita_escopo(afirmacao: str, conteudo_fonte: str) -> bool:
    afirmacao_normalizada = _normalizar(afirmacao)
    fonte_normalizada = _normalizar(conteudo_fonte)
    escopos = (
        ("adjudicacao compulsoria", ("adjudicacao compulsoria",)),
        (
            "direitos hereditarios",
            ("hereditario", "heranca", "coerdeiro", "quinhao"),
        ),
        ("coerdeiro", ("hereditario", "heranca", "coerdeiro")),
        ("alienado fiduciariamente", ("fiduciario", "alienacao fiduciaria")),
        ("cedulas de credito imobiliarias", ("cedula de credito",)),
        ("renuncia do usufruto", ("usufruto",)),
    )
    return all(
        marcador not in fonte_normalizada
        or any(termo in afirmacao_normalizada for termo in termos_de_escopo)
        for marcador, termos_de_escopo in escopos
    )


def _historico_para_prompt(dados: ConsultaRequest) -> str:
    texto = "\n".join(
        f"{mensagem.papel.upper()}: {mensagem.conteudo}"
        for mensagem in dados.historico[-10:]
    )
    return texto[-MAX_HISTORICO_PROMPT:]


def _consulta_para_recuperacao(dados: ConsultaRequest) -> str:
    pergunta = dados.consulta.strip()
    if not _pergunta_continua_contexto(pergunta):
        return _expandir_consulta_juridica(pergunta)

    perguntas_anteriores = [
        mensagem.conteudo[:350]
        for mensagem in dados.historico[-10:]
        if mensagem.papel.casefold() in {"usuario", "user"}
    ][-2:]
    return "\n".join([*perguntas_anteriores, pergunta])[-MAX_CONSULTA_RECUPERACAO:]


def _unir_resultados_busca(*grupos: list[dict]) -> list[dict]:
    resultados_por_id: dict[str, dict] = {}
    ordem: list[str] = []
    for grupo in grupos:
        for resultado in grupo:
            fonte_id = resultado.get("fonte_id") or resultado.get("chunk_id")
            if not fonte_id:
                continue
            if fonte_id not in resultados_por_id:
                ordem.append(fonte_id)
                resultados_por_id[fonte_id] = resultado
                continue
            if float(resultado.get("similaridade") or 0) > float(
                resultados_por_id[fonte_id].get("similaridade") or 0
            ):
                resultados_por_id[fonte_id] = resultado
    return [resultados_por_id[fonte_id] for fonte_id in ordem]


TEMAS_EXPLICITOS_CONSULTA = {
    "DOACAO": (
        r"\bdoa\w*\b",
        r"\bdoador\w*\b",
        r"\bdonatari\w*\b",
        r"\bliberalidade\b",
    ),
    "ATA_NOTARIAL": (r"\bata\s+notarial\b", r"\bnotarial\b"),
    "CESSAO": (r"\bcess\w*\b", r"\bcedente\b", r"\bcessionari\w*\b"),
    "COMPRA_VENDA": (
        r"\bcompra\b",
        r"\bvenda\b",
        r"\bcomprador\w*\b",
        r"\bvendedor\w*\b",
        r"\balienante\w*\b",
        r"\badquirente\w*\b",
    ),
    "INVENTARIO": (
        r"\binventari\w*\b",
        r"\bpartilh\w*\b",
        r"\binventariante\b",
    ),
}


ANCORAS_TEMAS_CONSULTA = {
    "DOACAO": ("doacao", "doador", "donatario", "liberalidade", "donativo"),
    "ATA_NOTARIAL": ("ata notarial",),
    "CESSAO": ("cessao", "cedente", "cessionario"),
    "COMPRA_VENDA": (
        "compra e venda",
        "compra",
        "venda",
        "comprador",
        "vendedor",
        "alienante",
        "adquirente",
    ),
    "INVENTARIO": (
        "inventario",
        "partilha",
        "inventariante",
        "herdeiro",
        "heranca",
        "espolio",
    ),
}

ESCOPO_ESPECIFICO_TEMA = {
    "DOACAO": ("usufruto", "inventario", "formal de partilha"),
}

ESCOPO_CONDICIONAL_COMPRA_VENDA = (
    (
        ("espólio", "inventariante", "de cujus", "falecido"),
        ("espólio", "inventariante", "inventário", "de cujus", "falecido", "falecida"),
    ),
    (
        ("incapaz", "menor", "numerário"),
        ("incapaz", "menor", "incapacidade", "numerário", "recursos próprios"),
    ),
    (
        ("leilão", "fiduciário", "consolidação da propriedade"),
        ("leilão", "fiduciário", "fiduciária", "consolidação"),
    ),
    (
        ("promessa", "compromisso", "promitente"),
        ("promessa", "compromisso", "promitente", "preliminar"),
    ),
    (
        ("fgts", "contrato habitacional", "financiamento"),
        ("fgts", "habitacional", "financiamento"),
    ),
    (
        ("imóvel rural", "ccir", "itr"),
        ("imóvel rural", "rural", "ccir", "itr"),
    ),
    (
        ("permuta", "torna", "permutante"),
        ("permuta", "torna", "permutante"),
    ),
    (
        ("usucapião", "usucapiente"),
        ("usucapião", "usucapiente"),
    ),
    (
        (
            "instituições financeiras",
            "crédito imobiliário",
            "instrumentos particulares",
        ),
        (
            "instituição financeira",
            "crédito imobiliário",
            "instrumento particular",
            "financiamento",
        ),
    ),
    (
        (
            "terrenos de marinha",
            "laudêmio",
            "certidão de autorização para transferência",
        ),
        ("terreno de marinha", "marinha", "laudêmio", "cat"),
    ),
)

CONSULTAS_COMPLEMENTARES_REQUISITOS_COMPRA_VENDA = (
    "escritura pública de imóveis: matrícula e certidão de inteiro teor, "
    "descrição do imóvel, ITBI e tributos municipais, débitos de condomínio, "
    "ônus reais e valores do negócio",
    "tabelião escritura pública de imóvel prova dominial do alienante capacidade "
    "do comparecente qualificação das partes regime de bens forma e meio de pagamento",
)

CONSULTAS_COMPLEMENTARES_REQUISITOS_INVENTARIO = (
    "escritura pública de inventário e partilha: Resolução CNJ n. 35, Código de "
    "Processo Civil e normas aplicáveis",
    "escritura pública de inventário extrajudicial: interessado incapaz, "
    "pagamento do quinhão hereditário ou meação em parte ideal, nomeação prévia "
    "de inventariante e documento de identidade do falecido",
    "documentos de identificação do falecido, certidão de óbito e certidões "
    "necessárias para a escritura de inventário extrajudicial",
)

PADRAO_PERGUNTA_GERAL_REQUISITOS = re.compile(
    r"\b(?:o que (?:se )?(?:precisa|preciso|e necessario|seria necessario)|"
    r"quais? (?:sao )?(?:os )?(?:documentos|requisitos)|"
    r"documentos? necessarios|documentacao necessaria|requisitos? gerais|checklist|"
    r"lista de documentos|"
    r"como (?:fazer|lavrar|formalizar))\b"
)


def _tema_explicito_consulta(pergunta: str) -> str | None:
    normalizada = _normalizar(pergunta)
    temas = [
        tema
        for tema, padroes in TEMAS_EXPLICITOS_CONSULTA.items()
        if any(re.search(padrao, normalizada) for padrao in padroes)
    ]
    return temas[0] if len(temas) == 1 else None


def _pergunta_pede_requisitos_gerais(pergunta: str) -> bool:
    return bool(PADRAO_PERGUNTA_GERAL_REQUISITOS.search(_normalizar(pergunta)))


def _fonte_transversal_compra_venda(fonte: dict) -> bool:
    conteudo = _conteudo_proprio_do_artigo(fonte)
    if not conteudo:
        return False

    if "ato translativo" in conteudo and "prova dominial" in conteudo:
        return True

    regra_geral_da_escritura = any(
        termo in conteudo
        for termo in (
            "forma e meio de pagamento",
            "capacidade do comparecente",
        )
    )
    regra_geral_imobiliaria = bool(
        re.search(
            r"\bescrituras?\b[\s\S]{0,180}\bimove(?:l|is)\b[\s\S]{0,100}\bdevem\s+conter\b",
            conteudo,
        )
    )
    return "escritura" in conteudo and (
        regra_geral_da_escritura or regra_geral_imobiliaria
    )


def _continua_regra_transversal_compra_venda(
    fonte: dict,
    resultados: list[dict],
) -> bool:
    artigo_contexto = fonte.get("artigo_contexto")
    documento_id = fonte.get("documento_id")
    if not artigo_contexto or not documento_id:
        return False
    return any(
        item.get("documento_id") == documento_id
        and _normalizar(item.get("artigo") or "") == _normalizar(artigo_contexto)
        and _fonte_transversal_compra_venda(item)
        for item in resultados
    )


def _fonte_tem_escopo_compra_venda_nao_mencionado(
    pergunta: str,
    fonte: dict,
) -> bool:
    conteudo = _conteudo_proprio_do_artigo(fonte)
    if not conteudo:
        return False

    pergunta_normalizada = _normalizar(pergunta)

    def contem_marcador(texto: str, marcador: str) -> bool:
        marcador_normalizado = _normalizar(marcador)
        return bool(re.search(rf"\b{re.escape(marcador_normalizado)}\b", texto))

    for marcadores_fonte, marcadores_pergunta in ESCOPO_CONDICIONAL_COMPRA_VENDA:
        possui_escopo = any(
            contem_marcador(conteudo, marcador) for marcador in marcadores_fonte
        )
        escopo_mencionado = any(
            contem_marcador(pergunta_normalizada, marcador)
            for marcador in marcadores_pergunta
        )
        if not possui_escopo or escopo_mencionado:
            continue
        escopo_rural = any(
            _normalizar(marcador) in {"imovel rural", "ccir", "itr"}
            for marcador in marcadores_fonte
        )
        if escopo_rural and (
            re.search(r"\brur\w*\b", conteudo) and re.search(r"\burban\w*\b", conteudo)
        ):
            continue
        escopo_maritimo = any(
            "marinha" in _normalizar(marcador) or "laudemio" in _normalizar(marcador)
            for marcador in marcadores_fonte
        )
        if escopo_maritimo and any(
            contem_marcador(conteudo, marcador)
            for marcador in (
                "matrícula",
                "certidão de inteiro teor",
                "pagamento do imposto de transmissão",
                "quitação das obrigações do alienante",
                "pacto antenupcial",
                "valores individuais",
            )
        ):
            continue
        return True
    return False


def _consultas_complementares_requisitos(pergunta: str) -> tuple[str, ...]:
    if not _pergunta_pede_requisitos_gerais(pergunta):
        return ()

    foco = _termos_foco_consulta(pergunta)
    consultas = (
        (f"{foco} documentos exigidos requisitos checklist do ato",)
        if foco
        else ()
    )
    tema = _tema_explicito_consulta(pergunta)
    complementos_especificos = (
        CONSULTAS_COMPLEMENTARES_REQUISITOS_INVENTARIO
        if tema == "INVENTARIO"
        else CONSULTAS_COMPLEMENTARES_REQUISITOS_COMPRA_VENDA
        if tema == "COMPRA_VENDA"
        else ()
    )
    return tuple(dict.fromkeys((*consultas, *complementos_especificos)))


def _conteudo_proprio_do_artigo(fonte: dict) -> str:
    conteudo = _normalizar(fonte.get("conteudo", ""))
    artigo = fonte.get("artigo")
    if not artigo:
        return conteudo

    numero = re.search(r"\d+(?:\.\d+)*", _normalizar(artigo))
    if not numero:
        return conteudo
    marcador = re.search(
        rf"\bart(?:igo)?\.?\s*{re.escape(numero.group())}(?![\d])",
        conteudo,
    )
    if not marcador:
        return ""

    restante = conteudo[marcador.end() :]
    limites = [
        correspondencia.start()
        for padrao in (
            r"(?im)^[ \t]*art(?:igo)?\.?[ \t]*\d+(?:\.\d+)*\b",
            r"(?im)^[ \t]*(?:subsecao|secao|capitulo)\s+(?:[ivxlcdm]+|\d+)\b",
        )
        if (correspondencia := re.search(padrao, restante))
    ]
    fim = min(limites) if limites else len(restante)
    return conteudo[marcador.start() : marcador.end() + fim]


def _fonte_corresponde_ao_tema(fonte: dict, tema: str) -> bool:
    conteudo = _conteudo_proprio_do_artigo(fonte)
    if not conteudo:
        return False
    if (
        tema == "INVENTARIO"
        and "formal de partilha" in conteudo
        and "inventario extrajudicial" not in conteudo
        and "escritura publica de inventario" not in conteudo
    ):
        return False
    if any(escopo in conteudo for escopo in ESCOPO_ESPECIFICO_TEMA.get(tema, ())):
        return False
    return any(
        re.search(rf"\b{re.escape(ancora)}\w*\b", conteudo)
        for ancora in ANCORAS_TEMAS_CONSULTA[tema]
    )


def _filtrar_resultados_por_tema(pergunta: str, resultados: list[dict]) -> list[dict]:
    tema = _tema_explicito_consulta(pergunta)
    if tema is None:
        return resultados

    correspondentes = [
        item
        for item in resultados
        if (
            tema == "COMPRA_VENDA"
            and _pergunta_pede_requisitos_gerais(pergunta)
            and (
                _fonte_transversal_compra_venda(item)
                or _continua_regra_transversal_compra_venda(item, resultados)
            )
            and not _fonte_tem_escopo_compra_venda_nao_mencionado(pergunta, item)
        )
        or (
            _fonte_corresponde_ao_tema(item, tema)
            and not (
                tema == "COMPRA_VENDA"
                and _pergunta_pede_requisitos_gerais(pergunta)
                and _fonte_tem_escopo_compra_venda_nao_mencionado(pergunta, item)
            )
        )
    ]
    if not correspondentes:
        return []

    if tema == "INVENTARIO":
        grupos: dict[tuple[str | None, str | None, str | None], list[dict]] = {}
        for item in correspondentes:
            if item.get("secao"):
                chave = (
                    item.get("documento_id"),
                    item.get("capitulo"),
                    item.get("secao"),
                )
                grupos.setdefault(chave, []).append(item)
        grupo_principal = max(grupos.values(), key=len, default=[])
        if len(grupo_principal) >= 2:
            ids_principais = {id(item) for item in grupo_principal}
            chave_principal = (
                grupo_principal[0].get("documento_id"),
                grupo_principal[0].get("capitulo"),
                grupo_principal[0].get("secao"),
            )
            fontes_diretas = {
                id(item)
                for item in correspondentes
                if item.get("artigo")
                and any(
                    expressao in _conteudo_proprio_do_artigo(item)
                    for expressao in (
                        "inventario extrajudicial",
                        "escritura publica de inventario",
                    )
                )
            }
            correspondentes = [
                item
                for item in resultados
                if id(item) in ids_principais
                or id(item) in fontes_diretas
                or (
                    item.get("secao")
                    and (
                        item.get("documento_id"),
                        item.get("capitulo"),
                        item.get("secao"),
                    )
                    == chave_principal
                )
            ]
    elif tema == "COMPRA_VENDA" and _pergunta_pede_requisitos_gerais(pergunta):
        grupos: dict[tuple[str | None, str | None, str | None], list[dict]] = {}
        for item in correspondentes:
            if item.get("secao"):
                chave = (
                    item.get("documento_id"),
                    item.get("capitulo"),
                    item.get("secao"),
                )
                grupos.setdefault(chave, []).append(item)
        grupo_principal = max(grupos.values(), key=len, default=[])
        if len(grupo_principal) >= 2:
            chave_principal = (
                grupo_principal[0].get("documento_id"),
                grupo_principal[0].get("capitulo"),
                grupo_principal[0].get("secao"),
            )
            correspondentes = [
                item
                for item in resultados
                if (
                    item.get("documento_id"),
                    item.get("capitulo"),
                    item.get("secao"),
                )
                == chave_principal
                and not _fonte_tem_escopo_compra_venda_nao_mencionado(pergunta, item)
                or (
                    (
                        _fonte_transversal_compra_venda(item)
                        or _continua_regra_transversal_compra_venda(item, resultados)
                    )
                    and not _fonte_tem_escopo_compra_venda_nao_mencionado(
                        pergunta, item
                    )
                )
            ]

    # Em perguntas gerais, um artigo isolado de outra seção pode citar o ato
    # incidentalmente (ex.: doação de bens inservíveis), sem integrar a seção
    # que o disciplina. Prioriza o grupo documental coeso encontrado na busca;
    # perguntas específicas continuam livres para recuperar a exceção indicada.
    termos_foco = _termos_foco_consulta(pergunta).split()
    if len(termos_foco) == 1:
        grupos: dict[tuple[str | None, str | None, str | None], list[dict]] = {}
        for item in correspondentes:
            if item.get("secao"):
                chave = (
                    item.get("documento_id"),
                    item.get("capitulo"),
                    item.get("secao"),
                )
                grupos.setdefault(chave, []).append(item)
        grupos_ordenados = sorted(grupos.values(), key=len, reverse=True)
        if (
            grupos_ordenados
            and len(grupos_ordenados[0]) >= 2
            and (
                len(grupos_ordenados) == 1
                or len(grupos_ordenados[0]) > len(grupos_ordenados[1])
            )
        ):
            correspondentes = grupos_ordenados[0]

    artigos_confirmados = {
        (item.get("documento_id"), _normalizar(item.get("artigo") or ""))
        for item in correspondentes
        if item.get("artigo")
    }
    return [
        item
        for item in resultados
        if item in correspondentes
        or (
            item.get("artigo")
            and (item.get("documento_id"), _normalizar(item.get("artigo") or ""))
            in artigos_confirmados
            and not (
                tema == "COMPRA_VENDA"
                and _pergunta_pede_requisitos_gerais(pergunta)
                and _fonte_tem_escopo_compra_venda_nao_mencionado(pergunta, item)
            )
        )
    ]


def _pergunta_continua_contexto(pergunta: str) -> bool:
    normalizada = _normalizar(pergunta).strip()
    # Só referências anafóricas inequívocas carregam a pergunta anterior.
    # "E o que precisa para um testamento?" nomeia um assunto novo, mesmo
    # que o ato ainda não esteja cadastrado em um vocabulário de temas.
    if _tema_explicito_consulta(normalizada):
        return False
    return bool(
        re.match(
            r"^(?:e\s+(?:quanto|nesse|nessa|isso|ele|ela)\b|"
            r"isso\b|nesse\s+caso\b|nessa\s+hipotese\b|"
            r"neste\s+caso\b|nesta\s+hipotese\b|"
            r"ele\b|ela\b|eles\b|elas\b|"
            r"qual\s+(?:o|a)\s+prazo\s+(?:disso|nesse\s+caso)\b)",
            normalizada,
        )
    )


def _expandir_consulta_juridica(pergunta: str) -> str:
    # A busca principal não deve substituir a pergunta real por um roteiro
    # pré-escrito para alguns atos: isso enviesava o ranking e a resposta.
    return pergunta


def _termos_foco_consulta(pergunta: str) -> str:
    """Consulta lexical complementar, sem presumir qual ato o usuário quis."""
    ignorados = {
        "precisa",
        "preciso",
        "precisam",
        "necessario",
        "necessaria",
        "necessarios",
        "necessarias",
        "abertura",
        "protocolo",
        "ato",
        "atos",
        "escritura",
        "escrituras",
        "publica",
        "publico",
        "checklist",
        "lavrar",
        "lavratura",
        "apresentar",
        "apresentacao",
        "levar",
        "realizar",
        "formalizar",
        "fazer",
        "quais",
        "qual",
        "quanto",
        "sobre",
        "para",
        "como",
        "onde",
        "quando",
        "isso",
        "esse",
        "essa",
        "deste",
        "dessa",
        "uma",
        "umas",
        "uns",
        "que",
        "sao",
        "documentos",
        "documento",
        "requisitos",
        "requisito",
    }
    termos = [
        termo
        for termo in re.findall(r"\b\w+\b", _normalizar(pergunta))
        if len(termo) >= 4 and termo not in ignorados
    ]
    return " ".join(dict.fromkeys(termos))[:160]


def _priorizar_fontes_de_pergunta_geral(
    pergunta: str, resultados: list[dict]
) -> list[dict]:
    """Evita completar uma regra central com hipóteses periféricas do mesmo livro."""
    if (
        len(resultados) < 4
        or len({item.get("documento_id") for item in resultados}) != 1
    ):
        return resultados
    if not re.search(
        r"\b(?:o que precisa|quais? documentos?|requisitos?|como fazer)\b",
        _normalizar(pergunta),
    ):
        return resultados
    if _tema_explicito_consulta(pergunta) == "INVENTARIO":
        # Inventário extrajudicial tem regras distribuídas por vários artigos;
        # cortar tudo que fique 0,10 abaixo do melhor trecho pode remover um
        # requisito específico. Dentro da seção principal, preservar a ordem
        # do documento ajuda o modelo a ler as regras como um conjunto.
        grupos: dict[tuple[str | None, str | None, str | None], list[dict]] = {}
        for item in resultados:
            if item.get("secao"):
                chave = (
                    item.get("documento_id"),
                    item.get("capitulo"),
                    item.get("secao"),
                )
                grupos.setdefault(chave, []).append(item)
        chave_principal = max(
            grupos, key=lambda chave: len(grupos[chave]), default=None
        )
        termos_foco = set(_termos_relevantes(_termos_foco_consulta(pergunta)))
        if _pergunta_pede_requisitos_gerais(pergunta):
            termos_foco |= _termos_relevantes(
                "documento documentos identidade identificação certidão apresentação"
            )
        return sorted(
            resultados,
            key=lambda item: (
                0
                if chave_principal
                == (
                    item.get("documento_id"),
                    item.get("capitulo"),
                    item.get("secao"),
                )
                else 1,
                -len(termos_foco & _termos_relevantes(item.get("conteudo") or "")),
                -float(item.get("similaridade") or 0.0),
                item.get("pagina") if item.get("pagina") is not None else 10**9,
                item.get("posicao") if item.get("posicao") is not None else 10**9,
            ),
        )
    melhor = max(float(item.get("similaridade") or 0) for item in resultados)
    if melhor <= 0:
        return resultados
    priorizados = [
        item
        for item in resultados
        if float(item.get("similaridade") or 0) >= melhor - 0.10
    ]
    if not priorizados:
        return resultados

    if _tema_explicito_consulta(
        pergunta
    ) != "COMPRA_VENDA" or not _pergunta_pede_requisitos_gerais(pergunta):
        return priorizados

    ids_priorizados = {item.get("fonte_id") for item in priorizados}
    regras_transversais = [
        item
        for item in resultados
        if (
            _fonte_transversal_compra_venda(item)
            or _continua_regra_transversal_compra_venda(item, resultados)
        )
        and item.get("fonte_id") not in ids_priorizados
    ]
    return [*priorizados, *regras_transversais]


def _limite_data_local_em_utc(data_local: date, fim_do_dia: bool) -> datetime:
    """Converte o dia informado na interface para o UTC ingênuo usado no banco."""
    horario = time.max if fim_do_dia else time.min
    instante_local = datetime.combine(data_local, horario, tzinfo=FUSO_LOCAL)
    return instante_local.astimezone(timezone.utc).replace(tzinfo=None)


def _referencia_visivel(resultado: dict) -> str:
    referencia = resultado["documento"]
    if resultado.get("artigo"):
        return f"{referencia}, {resultado['artigo']}"
    if resultado.get("pagina") is not None:
        return f"{referencia}, página {resultado['pagina']}"
    if resultado.get("localizacao"):
        return f"{referencia}, {resultado['localizacao']}"
    return f"{referencia}, trecho identificado"


def _citacao_tem_apoio(afirmacao: str, fonte: dict) -> bool:
    numeros_afirmacao = set(re.findall(r"\b\d+(?:[./-]\d+)*\b", afirmacao))
    numeros_fonte = set(re.findall(r"\b\d+(?:[./-]\d+)*\b", fonte["conteudo"]))
    if not numeros_afirmacao.issubset(numeros_fonte):
        return False
    if _negacao_contraditoria(afirmacao, fonte["conteudo"]):
        return False
    if not _afirmacao_respeita_escopo(afirmacao, fonte["conteudo"]):
        return False

    termos_afirmacao = _termos_relevantes(afirmacao)
    termos_fonte = _termos_relevantes(fonte["conteudo"])
    if not termos_afirmacao:
        return False

    # Em listas de alternativas, a sobreposição geral pode esconder um item
    # acrescentado sem respaldo. Verifica cada item quando há um marcador claro
    # de enumeração; em caso de dúvida, a resposta falha de forma conservadora.
    afirmacao_normalizada = _normalizar(afirmacao)
    marcador_lista = re.search(
        r"\b(?:admit\w*|inclu\w*|aceit\w*|compreend\w*|consist\w*)\b:?\s*",
        afirmacao_normalizada,
    )
    if marcador_lista:
        inicio_lista = marcador_lista.end()
        dois_pontos = afirmacao_normalizada.rfind(":")
        if dois_pontos >= inicio_lista:
            inicio_lista = dois_pontos + 1
        trecho_lista = afirmacao_normalizada[inicio_lista:]
        itens = [
            item.strip(" :;.!?()")
            for item in re.split(r"\s*,\s*|\s+e\s+", trecho_lista)
        ]
        itens = [item for item in itens if _termos_relevantes(item)]
        if len(itens) >= 2 and any(
            not _termos_relevantes(item).issubset(termos_fonte) for item in itens
        ):
            return False

    termos_comuns = termos_afirmacao & termos_fonte
    minimo = (
        len(termos_afirmacao)
        if len(termos_afirmacao) <= 2
        else max(
            2,
            math.ceil(len(termos_afirmacao) * 0.35),
        )
    )
    return len(termos_comuns) >= minimo


def _unidades_afirmativas(texto: str) -> list[str]:
    """Separa afirmações para não considerar um parágrafo inteiro fundamentado
    por uma única citação ao final de apenas uma das frases.
    """
    unidades: list[str] = []
    for linha in texto.splitlines():
        limpa = linha.strip()
        if not limpa or re.match(r"^#{1,6}\s+", limpa):
            continue
        limpa = re.sub(r"^[-*•]\s+", "", limpa)
        for unidade in _separar_unidades(limpa):
            conteudo = PADRAO_FONTE.sub("", unidade).strip(" -*•")
            if len(conteudo) >= 10 and _termos_relevantes(conteudo):
                unidades.append(unidade)
    return unidades


def _pontuacao_e_abreviacao(texto: str, indice: int) -> bool:
    """Evita tratar abreviações e números de artigo como fim de afirmação."""
    caractere = texto[indice]
    if caractere == ".":
        anterior = texto[indice - 1] if indice > 0 else ""
        seguinte = texto[indice + 1] if indice + 1 < len(texto) else ""
        if anterior.isdigit() and seguinte.isdigit():
            return True

        prefixo = texto[: indice + 1].rstrip()
        if re.search(r"\b(?:art|artigo|n|no|inc|p|fls|etc)\.$", prefixo, re.I):
            return True
        if re.search(r"\bart\.\s*\d+(?:\.\d+)*\.$", prefixo, re.I):
            return True
    return False


def _separar_unidades(texto: str) -> list[str]:
    """Divide por afirmações, sem fragmentar referências como ``Art. 1.277``."""
    unidades: list[str] = []
    inicio = 0
    for indice, caractere in enumerate(texto):
        if caractere not in ".!?;" or _pontuacao_e_abreviacao(texto, indice):
            continue
        if indice + 1 < len(texto) and not texto[indice + 1].isspace():
            continue
        restante = texto[indice + 1 :].lstrip()
        if restante.startswith("[FONTE-"):
            marcador = re.match(r"\s*\[FONTE-[^\]]+\]", texto[indice + 1 :])
            if marcador:
                fim_unidade = indice + 1 + marcador.end()
                unidades.append(texto[inicio:fim_unidade])
                inicio = fim_unidade
                continue
        unidades.append(texto[inicio : indice + 1])
        inicio = indice + 1
    if inicio < len(texto):
        unidades.append(texto[inicio:])
    return unidades


def _inicio_ultima_afirmacao(texto: str) -> int:
    inicio = 0
    for indice, caractere in enumerate(texto):
        if caractere == "\n":
            inicio = indice + 1
        elif (
            caractere in ".!?;"
            and not _pontuacao_e_abreviacao(texto, indice)
            and (indice + 1 == len(texto) or texto[indice + 1].isspace())
        ):
            inicio = indice + 1
    while inicio < len(texto) and texto[inicio].isspace():
        inicio += 1
    return inicio


def _chave_unidade(texto: str) -> str:
    texto_sem_fonte = PADRAO_FONTE.sub("", texto)
    texto_limpo = re.sub(r"^[-*•]\s+", "", texto_sem_fonte.strip())
    texto_limpo = texto_limpo.strip(" -*•.,;:")
    return re.sub(r"\s+", " ", texto_limpo).casefold()


def _limpar_afirmacao_validada(texto: str) -> str:
    texto = PADRAO_FONTE.sub("", texto).strip()
    texto = re.sub(r"^[-*•]\s+", "", texto)
    texto = re.sub(r"^(?:[IVXLCDM]+|[A-Z])\s*(?:[.)]|[-–—])\s+", "", texto)
    texto = re.sub(
        r"^(?:Além disso|Também|Ademais|Por outro lado),?\s+", "", texto, flags=re.I
    )
    return texto.rstrip(" .;:")


def _combinar_afirmacoes_validas(afirmacoes: list[str]) -> str | None:
    if len(afirmacoes) < 2:
        return None
    tokens = [list(re.finditer(r"\S+", item)) for item in afirmacoes]
    limite = min(map(len, tokens))
    comuns = 0
    while comuns < limite:
        valores = {_normalizar(item[comuns].group().strip(" ,;:.")) for item in tokens}
        if len(valores) != 1 or not next(iter(valores)):
            break
        comuns += 1
    if comuns < 3:
        return None

    prefixo = afirmacoes[0][: tokens[0][comuns - 1].end()].rstrip(" ,;:")
    complementos = [
        afirmacao[token[comuns - 1].end() :].strip(" ,;:")
        for afirmacao, token in zip(afirmacoes, tokens, strict=True)
    ]
    if any(not complemento for complemento in complementos):
        return None
    return f"{prefixo} {'; '.join(complementos)}"


def _formatar_afirmacoes_parciais(
    afirmacoes_validadas: list[tuple[str, str]],
    resultados_por_id: dict[str, dict],
    pergunta: str | None = None,
) -> str:
    agrupadas: dict[str, list[str]] = {}
    for afirmacao, fonte_id in afirmacoes_validadas:
        limpa = _limpar_afirmacao_validada(afirmacao)
        if not limpa:
            continue
        grupo = agrupadas.setdefault(fonte_id, [])
        termos_novos = {termo[:5] for termo in _termos_relevantes(limpa)}
        redundante = any(
            _chave_unidade(limpa) == _chave_unidade(item)
            or (
                len(termos_novos) >= 3
                and len(
                    termos_atuais := {termo[:5] for termo in _termos_relevantes(item)}
                )
                >= 3
                and len(termos_novos & termos_atuais)
                / min(len(termos_novos), len(termos_atuais))
                >= 0.7
            )
            for item in grupo
        )
        if not redundante:
            grupo.append(limpa)

    paragrafos = []
    for fonte_id, afirmacoes in agrupadas.items():
        if afirmacoes and ":" in afirmacoes[0]:
            fim_lista = 1
            while (
                fim_lista < len(afirmacoes)
                and afirmacoes[fim_lista]
                and afirmacoes[fim_lista][0].islower()
            ):
                fim_lista += 1
            if fim_lista > 1:
                itens = [item.rstrip(" .;:") for item in afirmacoes[:fim_lista]]
                paragrafos.append("; ".join(itens))
                afirmacoes = afirmacoes[fim_lista:]
        if not afirmacoes:
            continue
        combinada = _combinar_afirmacoes_validas(afirmacoes)
        if combinada and _citacao_tem_apoio(combinada, resultados_por_id[fonte_id]):
            paragrafos.append(combinada)
        else:
            paragrafos.extend(afirmacoes)
    frases: list[str] = []
    for item in paragrafos:
        limpa = item.strip(" .;:")
        if not limpa:
            continue
        if frases and limpa[0].islower():
            frases[-1] = f"{frases[-1]}; {limpa}"
        else:
            frases.append(limpa)
    corpo = " ".join(f"{item}." for item in frases)
    fundamentacao = _formatar_fundamentacao(
        list(dict.fromkeys(fonte_id for _, fonte_id in afirmacoes_validadas)),
        resultados_por_id,
    )
    if pergunta is None or _pergunta_pede_requisitos_gerais(pergunta):
        aviso_parcial = (
            "A base confirma os trechos citados, mas não confirma um checklist completo "
            "para esta pergunta; confira os demais requisitos nos documentos aplicáveis."
        )
    else:
        aviso_parcial = (
            "A base permite confirmar apenas os trechos citados; delimite o aspecto "
            "que deseja aprofundar."
        )
    complemento = "\n\n".join(item for item in (fundamentacao, aviso_parcial) if item)
    return f"{corpo}\n\n{complemento}" if complemento else corpo


def _juntar_referencias(referencias: list[str]) -> str:
    if len(referencias) < 2:
        return "".join(referencias)
    if len(referencias) == 2:
        return " e ".join(referencias)
    return f"{', '.join(referencias[:-1])} e {referencias[-1]}"


def _formatar_fundamentacao(
    fonte_ids: list[str],
    resultados_por_id: dict[str, dict],
) -> str:
    grupos: dict[str, dict[str, list[str]]] = {}
    for fonte_id in fonte_ids:
        fonte = resultados_por_id.get(fonte_id)
        if not fonte:
            continue
        documento = fonte["documento"]
        grupo = grupos.setdefault(documento, {"artigos": [], "outras": []})
        artigo = fonte.get("artigo")
        if artigo:
            numero = re.sub(r"(?i)^art(?:igo)?\.?\s*", "", artigo).strip()
            if numero and numero not in grupo["artigos"]:
                grupo["artigos"].append(numero)
        else:
            referencia = _referencia_visivel(fonte)
            if referencia not in grupo["outras"]:
                grupo["outras"].append(referencia)

    referencias = []
    for documento, grupo in grupos.items():
        artigos = grupo["artigos"]
        itens = []
        if artigos:
            rotulo = "Art." if len(artigos) == 1 else "arts."
            itens.append(f"{rotulo} {_juntar_referencias(artigos)}")
        itens.extend(
            referencia.removeprefix(f"{documento}, ") for referencia in grupo["outras"]
        )
        if itens:
            referencias.append(f"{documento}, {', '.join(itens)}")
    return f"Fundamentação: {_juntar_referencias(referencias)}." if referencias else ""


def _remover_referencias_inline(texto: str) -> str:
    texto = re.sub(
        r"\([^()]{0,100}?(?:art(?:igo)?\.?\s*\d|p[aá]gina\s*\d)[^()]*\)",
        "",
        texto,
        flags=re.IGNORECASE,
    )
    texto = re.sub(
        r"(?i)(?:\b(?:conforme|nos termos (?:do|de)|previsto (?:no|na)|"
        r"prevista (?:no|na))\s+)?(?:o\s+)?art(?:igo)?\.?\s*"
        r"\d+(?:\.\d+)*(?:\s*,?\s*§\s*\d+[º°o]?)?",
        "",
        texto,
    )
    texto = re.sub(r"(?i)\b(?:página|p\.)\s*\d+\b", "", texto)
    texto = re.sub(r"(?i)\b(?:do|da)\s+código de normas\b", "", texto)
    texto = re.sub(r"\(\s*\)|\[\s*\]", "", texto)
    texto = re.sub(r"\s+([,.;:])", r"\1", texto)
    texto = re.sub(r"([,;:])\s*([.!?])", r"\2", texto)
    texto = re.sub(r"[,;]\s*(?=\n|$)", "", texto)
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    return texto.strip()


def _atribuir_fontes_com_apoio_textual(
    resposta: str,
    resultados: list[dict],
) -> str:
    """Associa cada afirmação somente a um trecho que passe pelo verificador."""
    texto = PADRAO_FONTE.sub("", resposta)
    fontes_disponiveis = [item for item in resultados if item.get("id_contexto")]
    if not fontes_disponiveis:
        fontes_disponiveis = resultados

    insercoes: list[tuple[int, str]] = []
    cursor = 0
    for unidade in _unidades_afirmativas(texto):
        inicio = texto.find(unidade, cursor)
        if inicio < 0:
            continue
        cursor = inicio + len(unidade)
        afirmacao = unidade.strip()
        termos = _termos_relevantes(afirmacao)
        if not termos:
            continue

        apoiadores = [
            fonte
            for fonte in fontes_disponiveis
            if _citacao_tem_apoio(afirmacao, fonte)
        ]
        if not apoiadores:
            continue

        def pontuacao_fonte(fonte: dict) -> tuple[float, float]:
            termos_fonte = _termos_relevantes(fonte["conteudo"])
            cobertura = len(termos & termos_fonte) / len(termos)
            return cobertura, float(fonte.get("similaridade") or 0.0)

        fonte = max(apoiadores, key=pontuacao_fonte)
        identificador_contexto = fonte.get("id_contexto") or fonte["fonte_id"]
        insercoes.append((inicio + len(unidade), f" [{identificador_contexto}]"))

    for indice, marcador in reversed(insercoes):
        texto = f"{texto[:indice]}{marcador}{texto[indice:]}"
    return texto


def _trechos_literais_relacionados(
    pergunta: str,
    resultados: list[dict],
    citacoes_existentes: list[str],
    limite: int | None = None,
) -> tuple[str, list[str], str]:
    """Exibe evidência recuperada quando o texto gerado não passou na validação."""
    termos_pergunta = _termos_relevantes(_termos_foco_consulta(pergunta))
    if not termos_pergunta:
        termos_pergunta = _termos_relevantes(pergunta)
    tema = _tema_explicito_consulta(pergunta)
    grupos_do_tema: dict[tuple[str | None, str | None, str | None], int] = {}
    if tema:
        for fonte in resultados:
            if fonte.get("secao") and _fonte_corresponde_ao_tema(fonte, tema):
                chave = (
                    fonte.get("documento_id"),
                    fonte.get("capitulo"),
                    fonte.get("secao"),
                )
                grupos_do_tema[chave] = grupos_do_tema.get(chave, 0) + 1
    grupos_do_tema = {
        chave: quantidade
        for chave, quantidade in grupos_do_tema.items()
        if quantidade >= 2
    }
    if _pergunta_pede_requisitos_gerais(pergunta):
        # "O que precisa" também pode pedir documentos, embora a pessoa não
        # use essa palavra. Use esses termos apenas para escolher evidências
        # recuperadas, sem transformar a consulta em uma resposta pronta.
        termos_pergunta |= _termos_relevantes(
            "documento documentos identidade identificação certidão apresentação"
        )
    if limite is None:
        # O inventário costuma estar distribuído por mais artigos no acervo;
        # para outros atos, três excertos mantêm a resposta de contingência
        # concisa e reduzem menções periféricas.
        limite = 4 if tema == "INVENTARIO" else 3
    candidatos: list[tuple[float, int, float, dict, str]] = []
    for fonte in resultados:
        if fonte.get("fonte_id") in citacoes_existentes:
            continue
        for unidade in _separar_unidades(fonte.get("conteudo") or ""):
            trecho = " ".join(unidade.split())
            if len(trecho) < 45 or len(trecho) > 520:
                continue
            if re.match(r"^(?:ou|e|mas|nem)\b", _normalizar(trecho)):
                # Não exiba um fragmento que depende do item anterior do
                # chunk; sem esse contexto, a citação pode mudar de sentido.
                continue
            termos_comuns = termos_pergunta & _termos_relevantes(trecho)
            # Os resultados já passaram pela busca semântica e pelo filtro do
            # ato. Exigir dois termos literais aqui descartava regras corretas
            # redigidas com vocabulário normativo (por exemplo, "ato
            # translativo" para uma compra e venda).
            chave_tema = (
                fonte.get("documento_id"),
                fonte.get("capitulo"),
                fonte.get("secao"),
            )
            fonte_do_tema = tema is not None and (
                _fonte_corresponde_ao_tema(fonte, tema) or chave_tema in grupos_do_tema
            )
            fonte_transversal = tema == "COMPRA_VENDA" and (
                _fonte_transversal_compra_venda(fonte)
                or _continua_regra_transversal_compra_venda(fonte, resultados)
            )
            if not termos_comuns and not fonte_do_tema and not fonte_transversal:
                continue
            if not _citacao_tem_apoio(trecho, fonte):
                continue
            pontuacao = float(fonte.get("similaridade") or 0.0)
            pontuacao += min(len(termos_comuns), 4) * 0.035
            if chave_tema in grupos_do_tema:
                pontuacao += 0.05
            if fonte_transversal:
                pontuacao += 0.1
            candidatos.append(
                (
                    pontuacao,
                    len(termos_comuns),
                    float(fonte.get("similaridade") or 0.0),
                    fonte,
                    trecho,
                )
            )

    candidatos.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    selecionados: list[tuple[dict, str]] = []
    artigos_selecionados: set[tuple[str | None, str | None]] = set()
    for _, _, _, fonte, trecho in candidatos:
        chave = (
            fonte.get("documento_id"),
            fonte.get("artigo") or fonte.get("artigo_contexto"),
        )
        if chave in artigos_selecionados:
            continue
        artigos_selecionados.add(chave)
        selecionados.append((fonte, trecho))
        if len(selecionados) >= limite:
            break
    if not selecionados:
        return "", [], "BASE_INSUFICIENTE"

    linhas = [
        "Não consegui confirmar um checklist completo. Estes trechos da base tratam do assunto:"
    ]
    for fonte, trecho in selecionados:
        referencia = fonte.get("artigo") or fonte.get("artigo_contexto")
        if referencia:
            linhas.append(f"- {referencia}: “{trecho}”")
        else:
            linhas.append(f"- “{trecho}”")
    citacoes = list(dict.fromkeys(fonte["fonte_id"] for fonte, _ in selecionados))
    resultados_por_id = {fonte["fonte_id"]: fonte for fonte, _ in selecionados}
    fundamentacao = _formatar_fundamentacao(citacoes, resultados_por_id)
    if fundamentacao:
        linhas.extend(("", fundamentacao))
    return "\n".join(linhas), citacoes, "EVIDENCIA_PARCIAL"


def _fonte_tem_formato_checklist(resultados: list[dict]) -> bool:
    padrao_titulo = re.compile(
        r"\b(?:checklist|lista de (?:documentos|requisitos))\b"
    )
    padrao_item = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+\S")
    padrao_cabecalho = re.compile(r"\bdocumentos? necessarios\b")
    return any(
        padrao_titulo.search(_normalizar(fonte.get("documento", "")))
        or (
            padrao_cabecalho.search(_normalizar(fonte.get("conteudo", "")))
            and len(padrao_item.findall(fonte.get("conteudo", ""))) >= 2
        )
        for fonte in resultados
    )


def _grupo_tem_formato_checklist(fontes: list[dict]) -> bool:
    if _fonte_tem_formato_checklist(fontes):
        return True
    texto = _mesclar_chunks_checklist(fontes)
    return bool(
        re.search(r"\bdocumentos? necessarios\b", _normalizar(texto))
        and len(re.findall(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+\S", texto)) >= 2
    )


def _checklist_compativel_com_pergunta(
    pergunta: str,
    titulo: str,
    conteudo: str,
) -> bool:
    termos_pergunta = _termos_relevantes(_termos_foco_consulta(pergunta))
    if not termos_pergunta:
        return True

    termos_titulo = _termos_relevantes(titulo)
    termos_genericos_titulo = {
        "checklist",
        "lista",
        "documento",
        "documentos",
        "requisito",
        "requisitos",
        "necessario",
        "necessarios",
        "cartorio",
        "institucional",
        "ato",
        "atos",
        "escritura",
        "publica",
        "publico",
    }
    assunto_explicito_no_titulo = termos_titulo - termos_genericos_titulo
    if assunto_explicito_no_titulo:
        return bool(termos_pergunta & assunto_explicito_no_titulo)

    tema = _tema_explicito_consulta(pergunta)
    fonte_completa = {"artigo": None, "conteudo": conteudo}
    if tema and _fonte_corresponde_ao_tema(fonte_completa, tema):
        return True

    return bool(termos_pergunta & _termos_relevantes(conteudo))


def _resposta_checklist_satisfatoria(
    pergunta: str,
    resposta: str,
    resultados: list[dict],
) -> bool:
    if (
        not _pergunta_pede_requisitos_gerais(pergunta)
        or not _fonte_tem_formato_checklist(resultados)
    ):
        return True

    corpo = PADRAO_FUNDAMENTACAO.split(resposta, maxsplit=1)[0].strip()
    termos_foco = {
        termo[:5] for termo in _termos_relevantes(_termos_foco_consulta(pergunta))
    }
    termos_resposta = {termo[:5] for termo in _termos_relevantes(corpo)}
    menciona_o_assunto = not termos_foco or bool(termos_foco & termos_resposta)
    tem_desenvolvimento = len(corpo) >= 120 or len(_unidades_afirmativas(corpo)) >= 2
    etiquetas = _etiquetas_itens_checklist(resultados)
    itens_abordados = sum(bool(etiqueta & termos_resposta) for etiqueta in etiquetas)
    cobertura_minima = min(2, len(etiquetas))
    return (
        menciona_o_assunto
        and tem_desenvolvimento
        and itens_abordados >= cobertura_minima
    )


def _limpar_linha_checklist(linha: str) -> str:
    linha = linha.strip()
    if not linha or re.fullmatch(r"[_=\-–—\s]{3,}", linha):
        return ""

    if "@" in linha:
        cabecalho = re.search(
            r"(?i)\b(?:pessoa(?:s)?\s+j[uú]r[ií]dica(?:s)?|do\s+im[oó]vel|informar|"
            r"documentos?\s+necess[aá]rios)\b.*$",
            linha,
        )
        if cabecalho:
            linha = cabecalho.group(0)
        else:
            email = re.search(
                r"[\w.+-]+@[\w.-]+?\.(?:com\.br|org\.br|net\.br|gov\.br|"
                r"edu\.br|com|org|net|gov|edu|br)",
                linha,
                flags=re.IGNORECASE,
            )
            # Rodapés de contato às vezes ficam concatenados com a continuação
            # de um item durante a extração. Retém essa continuação após o e-mail.
            linha = linha[email.end() :].lstrip(" .,;:-–—") if email else ""

    linha = re.sub(
        r"(?i)\s*[\[(]?\s*(?:dispon[ií]vel em|pode ser obtida em|"
        r"solicite a via(?:\s+digital)?).*?$",
        "",
        linha,
    )
    if re.match(r"(?i)^(?:digital\s+e\s+encaminhe|nos\s+encaminhe)\b", linha):
        return ""

    linha = re.sub(
        r"\s*\([^)]*(?:https?://|www\.|dispon[ií]vel em|pode ser obtida em)[^)]*\)",
        "",
        linha,
        flags=re.IGNORECASE,
    )
    linha = re.sub(r"https?://\S+|www\.\S+", "", linha, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", linha).strip()


def _linha_inicia_cabecalho_checklist(linha: str, item_ativo: bool) -> bool:
    normalizada = _normalizar(linha)
    if linha.endswith(":"):
        if not item_ativo:
            return True
        return bool(PADRAO_CABECALHO_SECAO_CHECKLIST.match(normalizada))
    if item_ativo:
        return bool(PADRAO_CABECALHO_SECAO_CHECKLIST.match(normalizada))
    if len(linha) > 100 or re.search(r"[.!?;]$", linha):
        return False
    return bool(
        re.match(
            r"^(?:do\b|da\b|dos\b|das\b|para\s+pessoas?\b|pessoas?\s+juridicas?\b|"
            r"imovel\b|informar\b|documentos?\s+necessarios\b)",
            normalizada,
        )
    )


def _extrair_secoes_checklist(texto: str) -> list[tuple[str, list[str]]]:
    secoes: list[tuple[str, list[str]]] = []
    secao_atual = "Itens do checklist"
    item_atual = ""
    cabecalho_pendente = ""

    def obter_secao(titulo: str) -> list[str]:
        for titulo_existente, itens in secoes:
            if titulo_existente == titulo:
                return itens
        secoes.append((titulo, []))
        return secoes[-1][1]

    def salvar_item() -> None:
        nonlocal item_atual
        item = re.sub(r"\s+", " ", item_atual).strip(" ;,.–—-")
        item_atual = ""
        if len(item) >= 8:
            itens = obter_secao(secao_atual)
            chave = _normalizar(item)
            if all(_normalizar(existente) != chave for existente in itens):
                itens.append(item)

    def salvar_cabecalho() -> None:
        nonlocal secao_atual, cabecalho_pendente
        titulo = re.sub(r"\s+", " ", cabecalho_pendente).strip(" :;,.\t")
        cabecalho_pendente = ""
        if titulo:
            secao_atual = titulo
            obter_secao(secao_atual)

    for original in texto.splitlines():
        if re.fullmatch(r"[_=\-–—\s]{3,}", original.strip()):
            salvar_cabecalho()
            salvar_item()
            continue
        linha = _limpar_linha_checklist(original)
        if not linha:
            continue

        item = PADRAO_ITEM_CHECKLIST.match(linha)
        if item:
            salvar_cabecalho()
            salvar_item()
            item_atual = item.group(1).strip()
            continue

        if _linha_inicia_cabecalho_checklist(linha, bool(item_atual)):
            salvar_item()
            cabecalho_pendente = " ".join(
                parte for parte in (cabecalho_pendente, linha) if parte
            )
            if linha.endswith(":") or len(linha) <= 80:
                salvar_cabecalho()
            continue

        if cabecalho_pendente:
            cabecalho_pendente = f"{cabecalho_pendente} {linha}".strip()
            if linha.endswith(":") or len(cabecalho_pendente) >= 180:
                salvar_cabecalho()
            continue

        if item_atual:
            item_atual = f"{item_atual} {linha}".strip()
        elif not secoes:
            cabecalho_pendente = linha

    salvar_item()
    salvar_cabecalho()
    return [(titulo, itens) for titulo, itens in secoes if itens]


def _mesclar_chunks_checklist(fontes: list[dict]) -> str:
    por_pagina: dict[int, list[dict]] = {}
    for fonte in fontes:
        por_pagina.setdefault(int(fonte.get("pagina") or 0), []).append(fonte)

    paginas = []
    for pagina in sorted(por_pagina):
        texto_pagina = ""
        for fonte in sorted(
            por_pagina[pagina], key=lambda item: int(item.get("posicao") or 0)
        ):
            trecho = fonte.get("conteudo") or ""
            sobreposicao = 0
            maximo = min(500, len(texto_pagina), len(trecho))
            for tamanho in range(maximo, 0, -1):
                if texto_pagina[-tamanho:] == trecho[:tamanho]:
                    sobreposicao = tamanho
                    break
            texto_pagina += trecho[sobreposicao:] if sobreposicao else f"\n{trecho}"
        paginas.append(texto_pagina)
    return "\n\n".join(paginas)


def _etiquetas_itens_checklist(resultados: list[dict]) -> list[set[str]]:
    termos_genericos = {
        "apresentar",
        "apresentacao",
        "documento",
        "documentos",
        "certidao",
        "certidoes",
        "necessario",
        "necessaria",
        "exigido",
        "exigida",
        "informar",
        "informacao",
        "requisito",
        "requisitos",
        "fornecer",
        "comprovar",
    }
    grupos: dict[str, list[dict]] = {}
    for fonte in resultados:
        documento_id = fonte.get("documento_id")
        if documento_id:
            grupos.setdefault(str(documento_id), []).append(fonte)

    for fontes in grupos.values():
        if not _grupo_tem_formato_checklist(fontes):
            continue
        secoes = _extrair_secoes_checklist(_mesclar_chunks_checklist(fontes))
        etiquetas = []
        for _, itens in secoes:
            for item in itens:
                etiqueta = item.split(":", maxsplit=1)[0]
                termos = {
                    termo[:5]
                    for termo in _termos_relevantes(etiqueta)
                    if termo not in termos_genericos
                }
                if termos:
                    etiquetas.append(termos)
        if etiquetas:
            return etiquetas
    return []


def _responder_com_checklist_da_fonte(
    db: Session,
    pergunta: str,
    resultados: list[dict],
) -> tuple[str, list[dict], list[str], str] | None:
    if (
        not _pergunta_pede_requisitos_gerais(pergunta)
        or not _fonte_tem_formato_checklist(resultados)
    ):
        return None

    grupos: dict[str, list[dict]] = {}
    for fonte in resultados:
        documento_id = fonte.get("documento_id")
        if documento_id:
            grupos.setdefault(str(documento_id), []).append(fonte)

    grupos_ordenados = sorted(
        grupos.items(),
        key=lambda grupo: max(
            float(fonte.get("similaridade") or 0) for fonte in grupo[1]
        ),
        reverse=True,
    )
    for documento_id, fontes in grupos_ordenados:
        titulo = str(fontes[0].get("documento") or "Checklist institucional")
        if not _grupo_tem_formato_checklist(fontes):
            continue

        try:
            identificador = uuid.UUID(documento_id)
        except (TypeError, ValueError):
            continue

        paginas = (
            db.query(DocumentoPagina)
            .filter(DocumentoPagina.documento_id == identificador)
            .order_by(DocumentoPagina.pagina.asc())
            .all()
        )
        texto_integral = "\n\n".join(pagina.conteudo for pagina in paginas)
        if not texto_integral:
            texto_integral = _mesclar_chunks_checklist(fontes)
        if not _checklist_compativel_com_pergunta(
            pergunta,
            titulo,
            texto_integral,
        ):
            continue

        secoes = _extrair_secoes_checklist(texto_integral)
        total_itens = sum(len(itens) for _, itens in secoes)
        if total_itens < 2:
            continue

        texto_checklist_limpo = " ".join(
            linha
            for linha in (
                _limpar_linha_checklist(item)
                for item in texto_integral.splitlines()
            )
            if linha
        )
        texto_normalizado = " ".join(_normalizar(texto_checklist_limpo).split())
        itens_sem_apoio = [
            item
            for _, itens in secoes
            for item in itens
            if " ".join(_normalizar(item).split()) not in texto_normalizado
        ]
        if itens_sem_apoio:
            logger.warning(
                "Checklist %s não foi resumido porque %s item(ns) extraído(s) "
                "não coincidem literalmente com o documento",
                documento_id,
                len(itens_sem_apoio),
            )
            continue

        ato = re.sub(
            r"(?i)^(?:checklist|lista de documentos)\s*(?:de|para)?\s*",
            "",
            titulo,
        ).strip(" –—:-") or titulo
        linhas = [f"## Resumo do checklist: {ato}", ""]
        for secao, itens in secoes:
            linhas.extend((f"### {secao}", ""))
            linhas.extend(f"- {item}" for item in itens)
            linhas.append("")

        localizacao = "Documento integral"
        if paginas and all(not pagina.pagina_confiavel for pagina in paginas):
            localizacao = "Checklist completo (blocos lógicos)"
        fonte_integral = {
            "fonte_id": f"FONTE-{uuid.uuid4()}",
            "chunk_id": None,
            "documento_id": documento_id,
            "documento": titulo,
            "versao_documento": fontes[0].get("versao_documento"),
            "pagina": None,
            "localizacao": localizacao,
            "posicao": 1,
            "artigo": None,
            "conteudo": texto_integral,
            "similaridade": max(
                float(fonte.get("similaridade") or 0) for fonte in fontes
            ),
        }
        citacoes = [fonte_integral["fonte_id"]]
        fundamentacao = _formatar_fundamentacao(
            citacoes, {fonte_integral["fonte_id"]: fonte_integral}
        )
        resposta = "\n".join(linhas).rstrip()
        if fundamentacao:
            resposta = f"{resposta}\n\n{fundamentacao}"
        return resposta, [fonte_integral], citacoes, "extracao_checklist_fonte"
    return None


def _garantir_citacoes(
    resposta: str,
    resultados: list[dict],
    pergunta: str | None = None,
) -> tuple[str, list[str], str]:
    resposta = _atribuir_fontes_com_apoio_textual(resposta, resultados)
    resultados_por_id = {}
    for item in resultados:
        resultados_por_id[item["fonte_id"]] = item
        if item.get("id_contexto"):
            resultados_por_id[item["id_contexto"]] = item
    citados: list[str] = []
    unidades_citadas_por_bloco: set[str] = set()
    afirmacoes_validadas: list[tuple[str, str]] = []

    def validar(ocorrencia: re.Match) -> str:
        fonte_id = ocorrencia.group(1)
        fonte = resultados_por_id.get(fonte_id)
        if fonte is None:
            return ""
        prefixo = resposta[: ocorrencia.start()].rstrip()
        if prefixo.endswith((".", ";", ":")):
            prefixo = prefixo[:-1].rstrip()

        quebra_paragrafo = prefixo.rfind("\n\n")
        inicio_paragrafo = quebra_paragrafo + 2 if quebra_paragrafo >= 0 else 0
        paragrafo = prefixo[inicio_paragrafo:]
        paragrafo = re.sub(
            r"(?im)(?:^|\n)\s*(?:id\s+da\s+fonte|fonte)\s*$",
            "",
            paragrafo,
        ).strip()
        if PADRAO_FONTE.search(paragrafo):
            inicio = _inicio_ultima_afirmacao(prefixo)
            afirmacao = PADRAO_FONTE.sub("", prefixo[inicio:])
            if not _citacao_tem_apoio(afirmacao, fonte):
                return ""
            unidades_citadas_por_bloco.add(_chave_unidade(afirmacao))
            afirmacoes_validadas.append((afirmacao.strip(), fonte_id))
        else:
            # Uma citação ao final vale para a última afirmação; as anteriores
            # recebem IDs próprios pela associação textual automática acima.
            afirmacoes = _unidades_afirmativas(paragrafo)
            if not afirmacoes or not _citacao_tem_apoio(afirmacoes[-1], fonte):
                return ""
            unidades_citadas_por_bloco.add(_chave_unidade(afirmacoes[-1]))
            afirmacoes_validadas.append((afirmacoes[-1].strip(), fonte_id))

        citados.append(fonte["fonte_id"])
        return ocorrencia.group(0)

    resposta_validada = PADRAO_FONTE.sub(validar, resposta)
    citados = list(dict.fromkeys(citados))
    corpo = PADRAO_FUNDAMENTACAO.split(resposta_validada, maxsplit=1)[0].rstrip()
    unidades = _unidades_afirmativas(corpo)
    unidades_citadas = sum(
        bool(PADRAO_FONTE.search(unidade))
        or _chave_unidade(unidade) in unidades_citadas_por_bloco
        for unidade in unidades
    )
    cobertura = unidades_citadas / len(unidades) if unidades else 0.0

    corpo = PADRAO_FONTE.sub("", corpo)
    corpo = re.sub(r" +([.,;:])", r"\1", corpo)
    corpo = re.sub(r"[ \t]+\n", "\n", corpo).strip()
    corpo = _remover_referencias_inline(corpo)

    if not citados:
        return RESPOSTA_BASE_INSUFICIENTE, [], "BASE_INSUFICIENTE"

    if cobertura < 1.0:
        resposta_parcial = _formatar_afirmacoes_parciais(
            afirmacoes_validadas,
            resultados_por_id,
            pergunta,
        )
        if not resposta_parcial:
            return RESPOSTA_BASE_INSUFICIENTE, [], "BASE_INSUFICIENTE"
        return resposta_parcial, citados, "EVIDENCIA_PARCIAL"

    situacao = "EVIDENCIA_SUFFICIENTE"
    fundamentacao = _formatar_fundamentacao(citados, resultados_por_id)
    resposta_formatada = f"{corpo}\n\n{fundamentacao}" if fundamentacao else corpo
    return resposta_formatada, citados, situacao


class ContextoCompletoExcedido(ValueError):
    """Indica que um checklist administrativo não cabe no contexto seguro."""


def _montar_contexto(
    resultados: list[dict],
    limite: int = MAX_CONTEXTO,
    exigir_completo: bool = False,
) -> str:
    blocos = []
    tamanho = 0
    for resultado in resultados:
        id_contexto = f"FONTE-{len(blocos) + 1}"
        local = (
            f"Página: {resultado['pagina']}"
            if resultado.get("pagina") is not None
            else f"Localização: {resultado.get('localizacao') or 'trecho identificado'}"
        )
        metadados = ", ".join(
            item
            for item in (
                resultado.get("capitulo"),
                resultado.get("secao"),
                resultado.get("paragrafo"),
                resultado.get("inciso"),
            )
            if item
        )
        conteudo_normalizado = _normalizar(resultado["conteudo"])
        escopo_explicito = (
            "adjudicação compulsória extrajudicial"
            if "adjudicacao compulsoria" in conteudo_normalizado
            else "não identificado"
        )
        bloco = (
            f"ID DA FONTE: [{id_contexto}]\n"
            f"Documento: {resultado['documento']}\n"
            f"Natureza da fonte: {resultado.get('natureza_fonte', 'Documento institucional')}\n"
            f"{local}\n"
            f"Artigo comprovado no trecho: {resultado.get('artigo') or 'não identificado'}\n"
            f"Estrutura: {metadados or 'não identificada'}\n"
            f"Escopo específico expresso: {escopo_explicito}\n"
            f"Conteúdo:\n{resultado['conteudo']}"
        )
        if tamanho + len(bloco) > limite:
            if exigir_completo:
                raise ContextoCompletoExcedido
            continue
        resultado["id_contexto"] = id_contexto
        blocos.append(bloco)
        tamanho += len(bloco)
    return "\n\n".join(blocos)


def _extrair_lista_normativa(
    pergunta: str,
    resultados: list[dict],
) -> str | None:
    """Extrai listas normativas explícitas quando a pergunta pede requisitos."""
    normalizada = _normalizar(pergunta)
    if not _pergunta_pede_requisitos_gerais(pergunta):
        return None
    if re.search(r"\bdocument\w*\b", normalizada):
        return None

    termos_pergunta = _termos_relevantes(pergunta)
    fontes_disponiveis = [item for item in resultados if item.get("id_contexto")]
    if not fontes_disponiveis:
        fontes_disponiveis = resultados

    padrao_declaracao = re.compile(
        r"(?i)(?P<assunto>[^.!?:;\n]{3,120}?)\s+"
        r"(?P<verbo>conterá|deverá conter|deve conter)\s*:"
    )
    padrao_item = re.compile(
        r"(?<!\w)(?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)\s*[-–—]\s*"
    )

    for fonte in fontes_disponiveis:
        conteudo = fonte["conteudo"]
        for declaracao in padrao_declaracao.finditer(conteudo):
            assunto = declaracao.group("assunto").strip()
            termos_assunto = _termos_relevantes(assunto)
            if not termos_assunto:
                continue
            correspondencia = len(termos_assunto & termos_pergunta) / len(
                termos_assunto
            )
            if correspondencia < 0.5:
                continue

            restante = conteudo[declaracao.end() :]
            limite = re.search(
                r"(?i)\s+§\s*(?:\d+\s*[º°o]?|único)(?=\s|[.,;:]|$)",
                restante,
            )
            if limite:
                restante = restante[: limite.start()]
            marcadores = list(padrao_item.finditer(restante))
            if len(marcadores) < 2 or marcadores[0].start() > 16:
                continue

            itens = []
            for indice, marcador in enumerate(marcadores):
                fim = (
                    marcadores[indice + 1].start()
                    if indice + 1 < len(marcadores)
                    else len(restante)
                )
                item = restante[marcador.end() : fim]
                item = re.sub(r"\s+(?:e|,)\s*$", "", item, flags=re.IGNORECASE)
                item = re.sub(r"\s+", " ", item).strip(" ,;.")
                if item:
                    itens.append(item)
            if len(itens) < 2:
                continue

            verbo = declaracao.group("verbo").casefold()
            cabecalho = f"{assunto} {verbo}:"
            if not _citacao_tem_apoio(cabecalho, fonte) or any(
                not _citacao_tem_apoio(item, fonte) for item in itens
            ):
                continue

            corpo = "\n".join(
                f"- {item}{';' if indice + 1 < len(itens) else '.'}"
                for indice, item in enumerate(itens)
            )
            return f"{cabecalho}\n{corpo}"
    return None


def _salvar_historico(
    db: Session,
    usuario: Usuario,
    pergunta: str,
    resposta: str,
    confianca: float,
    situacao_resposta: str,
    resultados: list[dict],
    citacoes: list[str],
    metadados_ia: dict[str, object] | None = None,
) -> ConsultaHistorico:
    metadados = metadados_ia or {}
    modelo = metadados.get("modelo")
    modelo_texto = modelo if isinstance(modelo, str) else None
    modelo_versao = (
        modelo_texto.rsplit(":", 1)[1] if modelo_texto and ":" in modelo_texto else None
    )
    registro = ConsultaHistorico(
        usuario_id=usuario.id,
        pergunta=pergunta,
        resposta=resposta,
        confianca=confianca,
        confiavel=situacao_resposta == "EVIDENCIA_SUFFICIENTE",
        situacao_resposta=situacao_resposta,
        fonte_ids=json.dumps(citacoes),
        tipo_tarefa=str(metadados.get("tipo_tarefa") or "CONSULTA"),
        prompt_version=(
            str(metadados["prompt_version"])
            if metadados.get("prompt_version")
            else None
        ),
        modelo_ia=modelo_texto,
        modelo_versao=modelo_versao,
        parametros_ia=(
            dict(metadados["parametros"])
            if isinstance(metadados.get("parametros"), dict)
            else None
        ),
    )
    db.add(registro)
    db.flush()
    citadas = set(citacoes)
    for resultado in resultados:
        db.add(
            ConsultaFonte(
                consulta_id=registro.id,
                chunk_id=(
                    uuid.UUID(resultado["chunk_id"])
                    if resultado.get("chunk_id")
                    else None
                ),
                documento_id=(
                    uuid.UUID(resultado["documento_id"])
                    if resultado.get("documento_id")
                    else None
                ),
                fonte_id=resultado["fonte_id"],
                titulo_documento=resultado["documento"],
                versao_documento=resultado.get("versao_documento"),
                pagina=resultado.get("pagina"),
                localizacao=resultado.get("localizacao"),
                artigo=resultado.get("artigo"),
                trecho=resultado["conteudo"],
                pontuacao=resultado["similaridade"],
                citada=resultado["fonte_id"] in citadas,
                recuperada=True,
            )
        )
    db.commit()
    db.refresh(registro)
    return registro


def _fontes_por_consulta(
    db: Session, ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[ConsultaFonte]]:
    agrupadas = {consulta_id: [] for consulta_id in ids}
    if not ids:
        return agrupadas
    for fonte in (
        db.query(ConsultaFonte)
        .filter(ConsultaFonte.consulta_id.in_(ids))
        .order_by(ConsultaFonte.created_at.asc())
        .all()
    ):
        agrupadas.setdefault(fonte.consulta_id, []).append(fonte)
    return agrupadas


def _revisoes_por_consulta(
    db: Session,
    ids: list[uuid.UUID],
) -> dict[uuid.UUID, tuple[ConsultaRevisao, Usuario | None]]:
    if not ids:
        return {}
    revisoes = (
        db.query(ConsultaRevisao).filter(ConsultaRevisao.consulta_id.in_(ids)).all()
    )
    respondentes_ids = {
        revisao.respondido_por
        for revisao in revisoes
        if revisao.respondido_por is not None
    }
    respondentes = {
        usuario.id: usuario
        for usuario in (
            db.query(Usuario).filter(Usuario.id.in_(respondentes_ids)).all()
            if respondentes_ids
            else []
        )
    }
    return {
        revisao.consulta_id: (revisao, respondentes.get(revisao.respondido_por))
        for revisao in revisoes
    }


def _garantir_revisao_pendente(db: Session, consulta_id: uuid.UUID) -> None:
    existente = (
        db.query(ConsultaRevisao)
        .filter(ConsultaRevisao.consulta_id == consulta_id)
        .first()
    )
    if existente is not None:
        if existente.status == "ENCERRADA" and not existente.resposta_humana:
            existente.status = "PENDENTE"
            existente.encerrada_em = None
        return
    try:
        with db.begin_nested():
            db.add(
                ConsultaRevisao(
                    consulta_id=consulta_id,
                    status="PENDENTE",
                )
            )
            db.flush()
    except IntegrityError:
        # A unicidade por consulta torna reenvios simultâneos idempotentes.
        pass


@router.get("/historico", response_model=ConsultaHistoricoListResponse)
def listar_historico(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    usuario_id: uuid.UUID | None = None,
    data_inicial: date | None = None,
    data_final: date | None = None,
    avaliacao: str | None = None,
    evidencia: str | None = None,
    texto: str | None = None,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    consulta = db.query(ConsultaHistorico, Usuario).join(
        Usuario, Usuario.id == ConsultaHistorico.usuario_id
    )
    if usuario_atual.role != "ADMIN":
        consulta = consulta.filter(ConsultaHistorico.usuario_id == usuario_atual.id)
    elif usuario_id:
        consulta = consulta.filter(ConsultaHistorico.usuario_id == usuario_id)
    if data_inicial:
        consulta = consulta.filter(
            ConsultaHistorico.created_at
            >= _limite_data_local_em_utc(data_inicial, fim_do_dia=False)
        )
    if data_final:
        consulta = consulta.filter(
            ConsultaHistorico.created_at
            <= _limite_data_local_em_utc(data_final, fim_do_dia=True)
        )
    if avaliacao == "UTIL":
        consulta = consulta.filter(ConsultaHistorico.produtiva.is_(True))
    elif avaliacao == "NAO_UTIL":
        consulta = consulta.filter(ConsultaHistorico.produtiva.is_(False))
    elif avaliacao == "SEM_AVALIACAO":
        consulta = consulta.filter(ConsultaHistorico.produtiva.is_(None))
    if evidencia:
        consulta = consulta.filter(ConsultaHistorico.situacao_resposta == evidencia)
    if texto and texto.strip():
        termo = f"%{texto.strip()}%"
        consulta = consulta.filter(ConsultaHistorico.pergunta.ilike(termo))

    total = consulta.count()
    linhas = (
        consulta.order_by(ConsultaHistorico.created_at.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )
    fontes = _fontes_por_consulta(db, [registro.id for registro, _ in linhas])
    revisoes = _revisoes_por_consulta(db, [registro.id for registro, _ in linhas])
    items = []
    for registro, usuario in linhas:
        snapshots = fontes.get(registro.id, [])
        revisao_e_respondente = revisoes.get(registro.id)
        revisao = revisao_e_respondente[0] if revisao_e_respondente else None
        respondente = revisao_e_respondente[1] if revisao_e_respondente else None
        items.append(
            ConsultaHistoricoResponse(
                id=str(registro.id),
                usuario_id=str(registro.usuario_id),
                usuario_nome=usuario.nome,
                usuario_username=usuario.username,
                pergunta=registro.pergunta,
                resposta=registro.resposta,
                confianca=registro.confianca,
                confiavel=registro.confiavel,
                situacao_resposta=registro.situacao_resposta,
                fonte_ids=json.loads(registro.fonte_ids or "[]"),
                fontes=[
                    ConsultaFonteHistoricoResponse(
                        fonte_id=fonte.fonte_id,
                        documento_id=(
                            str(fonte.documento_id) if fonte.documento_id else None
                        ),
                        titulo_documento=fonte.titulo_documento,
                        versao_documento=fonte.versao_documento,
                        pagina=fonte.pagina,
                        localizacao=fonte.localizacao,
                        artigo=fonte.artigo,
                        trecho=fonte.trecho,
                        pontuacao=fonte.pontuacao,
                        citada=fonte.citada,
                        recuperada=fonte.recuperada,
                    )
                    for fonte in snapshots
                ],
                produtiva=registro.produtiva,
                feedback_motivo=registro.feedback_motivo,
                feedback_comentario=registro.feedback_comentario,
                tipo_tarefa=registro.tipo_tarefa,
                prompt_version=registro.prompt_version,
                modelo_ia=registro.modelo_ia,
                modelo_versao=registro.modelo_versao,
                parametros_ia=registro.parametros_ia,
                revisao=(
                    ConsultaRevisaoHistoricoResponse(
                        id=str(revisao.id),
                        status=revisao.status,
                        resposta_humana=revisao.resposta_humana,
                        respondido_por_nome=respondente.nome if respondente else None,
                        respondido_por_role=respondente.role if respondente else None,
                        respondida_em=revisao.respondida_em,
                        entendimento_documento_id=(
                            str(revisao.entendimento_documento_id)
                            if revisao.entendimento_documento_id
                            else None
                        ),
                    )
                    if revisao
                    else None
                ),
                created_at=registro.created_at,
            )
        )
    return ConsultaHistoricoListResponse(
        items=items,
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        total_paginas=math.ceil(total / por_pagina) if total else 0,
    )


@router.delete("/historico/{consulta_id}", status_code=204)
def excluir_registro_historico(
    consulta_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    registro = db.get(ConsultaHistorico, consulta_id)
    if registro is None:
        raise HTTPException(status_code=404, detail="Consulta não encontrada.")
    db.delete(registro)
    db.commit()
    return None


@router.patch("/{consulta_id}/feedback", status_code=204)
def avaliar_resposta(
    consulta_id: str,
    dados: ConsultaFeedbackRequest,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    try:
        identificador = uuid.UUID(consulta_id)
    except ValueError as erro:
        raise HTTPException(
            status_code=404, detail="Consulta não encontrada."
        ) from erro
    registro = db.get(ConsultaHistorico, identificador)
    if registro is None:
        raise HTTPException(status_code=404, detail="Consulta não encontrada.")
    if registro.usuario_id != usuario_atual.id:
        raise HTTPException(
            status_code=403, detail="Você não pode avaliar esta resposta."
        )
    registro.produtiva = dados.produtiva
    registro.feedback_motivo = dados.motivo if not dados.produtiva else None
    registro.feedback_comentario = (
        dados.comentario.strip()
        if not dados.produtiva and dados.comentario and dados.comentario.strip()
        else None
    )
    if not dados.produtiva:
        _garantir_revisao_pendente(db, registro.id)
    else:
        revisao = (
            db.query(ConsultaRevisao)
            .filter(ConsultaRevisao.consulta_id == registro.id)
            .first()
        )
        if revisao and revisao.status in {"PENDENTE", "EM_ANALISE"}:
            revisao.status = "ENCERRADA"
            revisao.encerrada_em = utc_now()
    db.commit()
    return None


@router.post("", response_model=ConsultaResponse)
def consultar(
    dados: ConsultaRequest,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    inicio_total = perf_counter()
    pergunta = dados.consulta.strip()
    inicio_recuperacao = perf_counter()
    consulta_recuperacao = _consulta_para_recuperacao(dados)

    def buscar_documentos() -> list[dict]:
        candidatos = buscar_chunks_semelhantes(db, consulta_recuperacao, limite=16)
        foco = _termos_foco_consulta(pergunta)
        if foco and _normalizar(foco) != _normalizar(consulta_recuperacao):
            candidatos_foco = buscar_chunks_semelhantes(db, foco, limite=16)
            # Intercala a pergunta e o assunto para manter trechos dos dois focos.
            intercalados = []
            for indice in range(max(len(candidatos), len(candidatos_foco))):
                if indice < len(candidatos):
                    intercalados.append(candidatos[indice])
                if indice < len(candidatos_foco):
                    intercalados.append(candidatos_foco[indice])
            candidatos = intercalados
        consultas_complementares = _consultas_complementares_requisitos(pergunta)
        candidatos_complementares = [
            buscar_chunks_semelhantes(db, consulta_complementar, limite=16)
            for consulta_complementar in consultas_complementares
        ]
        candidatos = _unir_resultados_busca(candidatos, *candidatos_complementares)
        return _priorizar_fontes_de_pergunta_geral(
            pergunta, _filtrar_resultados_por_tema(pergunta, candidatos)
        )[:16]

    resultados_entendimentos = buscar_entendimentos_publicados(
        db,
        consulta_recuperacao,
    )
    resultados_revisoes = (
        []
        if resultados_entendimentos
        else buscar_respostas_revisadas_admin(db, consulta_recuperacao)
    )
    nivel_fontes = (
        "ENTENDIMENTOS"
        if resultados_entendimentos
        else "REVISOES"
        if resultados_revisoes
        else "DOCUMENTOS"
    )
    resultados = resultados_entendimentos or resultados_revisoes
    if not resultados:
        resultados = buscar_documentos()
    tempo_recuperacao = perf_counter() - inicio_recuperacao
    if not resultados:
        resposta = (
            "Não há base documental suficiente para responder. Os anexos privados da "
            "aba Análise não participam desta Consulta. Para usar um documento aqui, "
            "cadastre-o em Documentos e confirme que está PRONTO, LIBERADO e APROVADO."
        )
        registro = _salvar_historico(
            db, usuario_atual, pergunta, resposta, 0.0, "BASE_INSUFICIENTE", [], []
        )
        logger.info(
            "Consulta sem base: recuperação=%.2fs total=%.2fs",
            tempo_recuperacao,
            perf_counter() - inicio_total,
        )
        return ConsultaResponse(
            id=str(registro.id),
            consulta=pergunta,
            resposta=resposta,
            confianca=0.0,
            confiavel=False,
            situacao_resposta="BASE_INSUFICIENTE",
            citacoes_verificadas=[],
            resultados=[],
        )

    inicio_geracao = perf_counter()

    def responder_com_fontes(fontes: list[dict]):
        if "DOCUMENTOS" in nivel_fontes:
            resposta_checklist = _responder_com_checklist_da_fonte(
                db,
                pergunta,
                fontes,
            )
            if resposta_checklist:
                (
                    resposta,
                    fontes_checklist,
                    citacoes_checklist,
                    metodo_checklist,
                ) = resposta_checklist
                fontes[:] = fontes_checklist
                metadados = {
                    "modelo": metodo_checklist,
                    "prompt_version": "checklist-fonte.2",
                    "tipo_tarefa": "CONSULTA",
                    "parametros": {"metodo": "extracao_estruturada_literal"},
                }
                return (
                    resposta,
                    citacoes_checklist,
                    "EVIDENCIA_SUFFICIENTE",
                    metadados,
                )

        usar_entendimento_integral = nivel_fontes == "ENTENDIMENTOS"
        try:
            contexto = _montar_contexto(
                fontes,
                limite=MAX_CONTEXTO,
                exigir_completo=usar_entendimento_integral,
            )
        except ContextoCompletoExcedido:
            return (
                "O entendimento publicado excede o contexto seguro desta consulta. "
                "Não vou resumir apenas parte da fonte como se ela estivesse completa; "
                "peça ao administrador que divida o conteúdo em partes menores.",
                [],
                "EVIDENCIA_PARCIAL",
                {"modelo": "entendimento_excede_contexto", "parametros": {}},
            )
        resposta_enumerada = (
            None
            if nivel_fontes != "DOCUMENTOS"
            else _extrair_lista_normativa(pergunta, fontes)
        )
        if resposta_enumerada:
            resposta_validada, fontes_citadas, situacao = _garantir_citacoes(
                resposta_enumerada, fontes, pergunta
            )
            if situacao == "EVIDENCIA_SUFFICIENTE":
                metadados = {
                    "modelo": "extracao_normativa",
                    "prompt_version": "lista_normativa.1",
                    "tipo_tarefa": "CONSULTA",
                    "parametros": {"metodo": "extracao_estruturada_validada"},
                }
                return resposta_validada, fontes_citadas, situacao, metadados

        argumentos_geracao: dict[str, object] = {
            "pergunta": pergunta,
            "contexto": contexto,
            "historico": _historico_para_prompt(dados),
        }
        resposta_modelo = gerar_resposta(**argumentos_geracao)
        if _resposta_direta_em_portugues(resposta_modelo):
            resposta_validada, fontes_citadas, situacao = _garantir_citacoes(
                resposta_modelo, fontes, pergunta
            )
        else:
            resposta_validada = RESPOSTA_FORMATO_INVALIDO
            fontes_citadas = []
            situacao = "BASE_INSUFICIENTE"
            logger.warning("Consulta descartada por idioma ou formato incompatível")

        if situacao in {"BASE_INSUFICIENTE", "EVIDENCIA_PARCIAL"}:
            texto_literal, fontes_literais, situacao_literal = (
                _trechos_literais_relacionados(pergunta, fontes, [])
            )
            if fontes_literais:
                resposta_validada = texto_literal
                fontes_citadas = fontes_literais
                situacao = situacao_literal

        if not _resposta_checklist_satisfatoria(
            pergunta,
            resposta_validada,
            fontes,
        ):
            resposta_checklist = _responder_com_checklist_da_fonte(
                db,
                pergunta,
                fontes,
            )
            if resposta_checklist:
                (
                    resposta_validada,
                    fontes_checklist,
                    fontes_citadas,
                    metodo_checklist,
                ) = resposta_checklist
                resultados[:] = fontes_checklist
                situacao = "EVIDENCIA_SUFFICIENTE"
                metadados = {
                    "modelo": metodo_checklist,
                    "prompt_version": "checklist-fonte.1",
                    "tipo_tarefa": "CONSULTA",
                    "parametros": {"metodo": "extracao_estruturada_validada"},
                }
                return (
                    resposta_validada,
                    fontes_citadas,
                    situacao,
                    metadados,
                )

            texto_literal, fontes_literais, situacao_literal = (
                _trechos_literais_relacionados(pergunta, fontes, [], limite=8)
            )
            if fontes_literais:
                return (
                    texto_literal,
                    fontes_literais,
                    situacao_literal,
                    obter_metadados_consulta(),
                )
            return (
                RESPOSTA_BASE_INSUFICIENTE,
                [],
                "BASE_INSUFICIENTE",
                obter_metadados_consulta(),
            )
        return (
            resposta_validada,
            fontes_citadas,
            situacao,
            obter_metadados_consulta(),
        )

    resposta = RESPOSTA_BASE_INSUFICIENTE
    citacoes: list[str] = []
    situacao_resposta = "BASE_INSUFICIENTE"
    metadados_ia = None
    entendimento_excede_contexto = False

    if nivel_fontes != "DOCUMENTOS":
        resposta, citacoes, situacao_resposta, metadados_ia = responder_com_fontes(
            resultados
        )
        entendimento_excede_contexto = isinstance(
            metadados_ia, dict
        ) and metadados_ia.get("modelo") == "entendimento_excede_contexto"
        if (
            situacao_resposta != "EVIDENCIA_SUFFICIENTE"
            and nivel_fontes == "ENTENDIMENTOS"
            and not entendimento_excede_contexto
        ):
            resultados_revisoes = buscar_respostas_revisadas_admin(
                db, consulta_recuperacao
            )
            if resultados_revisoes:
                resultados = _unir_resultados_busca(resultados, resultados_revisoes)
                nivel_fontes = "ENTENDIMENTOS_E_REVISOES"
                resposta, citacoes, situacao_resposta, metadados_ia = (
                    responder_com_fontes(resultados)
                )

    if (
        nivel_fontes != "DOCUMENTOS"
        and situacao_resposta != "EVIDENCIA_SUFFICIENTE"
        and not entendimento_excede_contexto
    ):
        resultados_documentais = buscar_documentos()
        if resultados_documentais:
            resultados = _unir_resultados_busca(resultados, resultados_documentais)
            nivel_fontes = f"{nivel_fontes}_E_DOCUMENTOS"
            resposta, citacoes, situacao_resposta, metadados_ia = responder_com_fontes(
                resultados
            )

    if nivel_fontes == "DOCUMENTOS":
        resposta, citacoes, situacao_resposta, metadados_ia = responder_com_fontes(
            resultados
        )

    tempo_geracao = perf_counter() - inicio_geracao
    confianca = resultados[0]["similaridade"]
    registro = _salvar_historico(
        db,
        usuario_atual,
        pergunta,
        resposta,
        confianca,
        situacao_resposta,
        resultados,
        citacoes,
        metadados_ia=metadados_ia,
    )
    fontes_utilizadas = [item for item in resultados if item["fonte_id"] in citacoes]
    logger.info(
        "Consulta concluída: fontes=%s recuperação=%.2fs geração=%.2fs total=%.2fs",
        len(fontes_utilizadas),
        tempo_recuperacao,
        tempo_geracao,
        perf_counter() - inicio_total,
    )
    return ConsultaResponse(
        id=str(registro.id),
        consulta=pergunta,
        resposta=resposta,
        confianca=confianca,
        confiavel=situacao_resposta == "EVIDENCIA_SUFFICIENTE",
        situacao_resposta=situacao_resposta,
        citacoes_verificadas=citacoes,
        resultados=fontes_utilizadas,
    )
