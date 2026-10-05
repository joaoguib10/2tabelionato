import re
import unicodedata
import uuid

from sqlalchemy.orm import Session

from app.models import (
    ConsultaHistorico,
    ConsultaRevisao,
    Documento,
    DocumentoChunk,
    Usuario,
)
from app.services.document_eligibility import condicoes_consulta

MAX_CHUNKS_ENTENDIMENTOS = 2_000
MAX_REVISOES_RESPONDIDAS = 1_000
MAX_FONTES_HUMANAS = 6

PALAVRAS_IGNORADAS = {
    "a",
    "as",
    "ao",
    "aos",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "essa",
    "esse",
    "esta",
    "este",
    "foi",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "pela",
    "pelas",
    "pelo",
    "pelos",
    "por",
    "qual",
    "quais",
    "que",
    "se",
    "sem",
    "sao",
    "ser",
    "um",
    "uma",
    "umas",
    "uns",
    "precisa",
    "precisam",
    "necessario",
    "necessaria",
    "necessarios",
    "necessarias",
    "abertura",
    "protocolo",
    "ato",
    "atos",
    "checklist",
    "publica",
    "publico",
    "escritura",
    "escrituras",
    "lavrar",
    "lavratura",
    "apresentar",
    "apresentacao",
    "levar",
    "realizar",
    "formalizar",
    "documento",
    "documentos",
    "documentacao",
    "escritura",
    "escrituras",
    "fazer",
    "lavrar",
    "lavratura",
    "requisito",
    "requisitos",
    "sobre",
    "deve",
    "devem",
    "pode",
    "podem",
    "tem",
    "ter",
}

ALIAS_TEMAS = {
    "COMPRA_VENDA": {
        "compra",
        "venda",
        "comprador",
        "compradora",
        "vendedor",
        "vendedora",
        "alienante",
        "adquirente",
        "imovel",
    },
    "INVENTARIO": {
        "inventario",
        "inventariante",
        "partilha",
        "herdeiro",
        "heranca",
        "espolio",
    },
    "DOACAO": {"doacao", "doador", "donatario", "liberalidade"},
    "ATA_NOTARIAL": {"ata", "notarial", "notario"},
    "CESSAO": {"cessao", "cedente", "cessionario"},
}

REGEX_IDENTIFICADOR_PESSOAL = re.compile(
    r"(?i)(?:\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|"
    r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b|"
    r"\b\d{11,14}\b|\b[^\s@]+@[^\s@]+\.[^\s@]+\b|"
    r"\b(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?9?\d{4}[-. ]?\d{4}\b)"
)


def _normalizar(texto: str) -> str:
    sem_acentos = unicodedata.normalize("NFD", texto.casefold())
    return "".join(
        caractere
        for caractere in sem_acentos
        if unicodedata.category(caractere) != "Mn"
    )


def _tokens(texto: str) -> set[str]:
    tokens = set()
    for token in re.findall(r"\b[\w]+\b", _normalizar(texto)):
        if len(token) < 3 or token in PALAVRAS_IGNORADAS:
            continue
        if token.endswith("oes"):
            token = f"{token[:-3]}ao"
        elif token.endswith("s"):
            token = token[:-1]
        tokens.add(token)
    return tokens


def _tema(texto: str) -> str | None:
    tokens = _tokens(texto)
    temas = [
        nome
        for nome, aliases in ALIAS_TEMAS.items()
        if tokens & {alias.rstrip("s") for alias in aliases}
    ]
    return temas[0] if len(temas) == 1 else None


def _pontuar_consulta(texto_consulta: str, texto_alvo: str) -> float:
    termos_consulta = _tokens(texto_consulta)
    if not termos_consulta:
        return 0.0
    termos_alvo = _tokens(texto_alvo)
    tema = _tema(texto_consulta)
    aliases_tema = {alias.rstrip("s") for alias in ALIAS_TEMAS[tema]} if tema else set()
    termos_especificos = termos_consulta - aliases_tema
    termos_correspondentes = termos_consulta & termos_alvo
    tema_correspondente = bool(termos_correspondentes & aliases_tema)

    if tema and not tema_correspondente:
        return 0.0
    if termos_especificos and not (termos_especificos & termos_alvo):
        return 0.0

    minimo = 1 if len(termos_consulta) <= 2 else 2
    if not tema and len(termos_correspondentes) < minimo:
        return 0.0

    proporcao = len(termos_correspondentes) / len(termos_consulta)
    return round(min(0.99, 0.55 + proporcao * 0.4), 4)


def _resultado_chunk(
    chunk: DocumentoChunk,
    documento: Documento,
    pontuacao: float,
) -> dict:
    artigo_confirmado = getattr(chunk, "artigo_confirmado", False) is True
    pagina_confiavel = getattr(chunk, "pagina_confiavel", True) is not False
    return {
        "fonte_id": f"FONTE-{chunk.id}",
        "chunk_id": str(chunk.id),
        "documento_id": str(documento.id),
        "documento": documento.titulo,
        "versao_documento": documento.versao,
        "pagina": chunk.pagina if pagina_confiavel else None,
        "localizacao": chunk.localizacao,
        "posicao": chunk.posicao,
        "artigo": chunk.artigo if artigo_confirmado else None,
        "artigo_contexto": chunk.artigo,
        "capitulo": chunk.capitulo,
        "secao": chunk.secao,
        "paragrafo": chunk.paragrafo,
        "inciso": chunk.inciso,
        "conteudo": chunk.conteudo,
        "similaridade": pontuacao,
        "natureza_fonte": "Entendimento administrativo publicado",
    }


def buscar_entendimentos_publicados(
    db: Session,
    consulta: str,
    limite: int = MAX_FONTES_HUMANAS,
) -> list[dict]:
    """Seleciona o entendimento mais pertinente e retorna seu conteúdo integral."""
    linhas = (
        db.query(DocumentoChunk, Documento)
        .join(Documento, Documento.id == DocumentoChunk.documento_id)
        .filter(*condicoes_consulta(), Documento.tipo == "ENTENDIMENTO")
        .order_by(Documento.aprovado_em.desc(), Documento.created_at.desc())
        .limit(MAX_CHUNKS_ENTENDIMENTOS)
        .all()
    )

    ranqueados = []
    for chunk, documento in linhas:
        texto_busca = " ".join(
            item
            for item in (documento.titulo, documento.descricao, chunk.conteudo)
            if item
        )
        pontuacao = _pontuar_consulta(consulta, texto_busca)
        if pontuacao > 0:
            ranqueados.append(
                (
                    pontuacao,
                    documento.aprovado_em or documento.created_at,
                    chunk,
                    documento,
                )
            )
    ranqueados.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if ranqueados:
        documento_relevante = ranqueados[0][3]
        chunks_completos = (
            db.query(DocumentoChunk, Documento)
            .join(Documento, Documento.id == DocumentoChunk.documento_id)
            .filter(
                *condicoes_consulta(),
                Documento.id == documento_relevante.id,
                Documento.tipo == "ENTENDIMENTO",
            )
            .order_by(DocumentoChunk.posicao.asc(), DocumentoChunk.pagina.asc())
            .all()
        )
        if chunks_completos:
            return [
                _resultado_chunk(
                    chunk,
                    documento,
                    _pontuar_consulta(
                        consulta,
                        " ".join(
                            item
                            for item in (
                                documento.titulo,
                                documento.descricao,
                                chunk.conteudo,
                            )
                            if item
                        ),
                    ),
                )
                for chunk, documento in chunks_completos
            ]
    return [
        _resultado_chunk(chunk, documento, pontuacao)
        for pontuacao, _, chunk, documento in ranqueados[:limite]
    ]


def buscar_respostas_revisadas_admin(
    db: Session,
    consulta: str,
    limite: int = MAX_FONTES_HUMANAS,
) -> list[dict]:
    """Busca correções respondidas por ADMIN sem reutilizar perguntas ou autores.

    Respostas com identificadores pessoais evidentes ficam fora da recuperação
    compartilhada. Revisões já encaminhadas para generalização também ficam fora
    enquanto seu entendimento ainda não estiver publicado.
    """
    linhas = (
        db.query(ConsultaRevisao, ConsultaHistorico.pergunta)
        .join(ConsultaHistorico, ConsultaHistorico.id == ConsultaRevisao.consulta_id)
        .join(Usuario, Usuario.id == ConsultaRevisao.respondido_por)
        .filter(
            ConsultaRevisao.status.in_({"RESPONDIDA", "ENCERRADA"}),
            ConsultaRevisao.resposta_humana.is_not(None),
            ConsultaRevisao.entendimento_documento_id.is_(None),
            Usuario.role == "ADMIN",
        )
        .order_by(ConsultaRevisao.respondida_em.desc())
        .limit(MAX_REVISOES_RESPONDIDAS)
        .all()
    )

    ranqueados = []
    for revisao, pergunta_original in linhas:
        resposta = revisao.resposta_humana.strip()
        if not resposta or REGEX_IDENTIFICADOR_PESSOAL.search(resposta):
            continue
        pontuacao = _pontuar_consulta(
            consulta,
            f"{pergunta_original} {resposta}",
        )
        if pontuacao <= 0:
            continue
        ranqueados.append((pontuacao, revisao.respondida_em, revisao, resposta))

    ranqueados.sort(
        key=lambda item: (item[0], item[1] or item[2].created_at), reverse=True
    )
    resultados = []
    for pontuacao, _, revisao, resposta in ranqueados[:limite]:
        identificador = uuid.UUID(str(revisao.id))
        resultados.append(
            {
                "fonte_id": f"FONTE-{identificador}",
                "chunk_id": None,
                "documento_id": None,
                "documento": "Resposta revisada pelo ADMIN",
                "versao_documento": None,
                "pagina": None,
                "localizacao": "Revisão administrativa",
                "posicao": 1,
                "artigo": None,
                "artigo_contexto": None,
                "capitulo": None,
                "secao": None,
                "paragrafo": None,
                "inciso": None,
                "conteudo": resposta,
                "similaridade": pontuacao,
                "natureza_fonte": "Resposta humana revisada pelo ADMIN",
            }
        )
    return resultados
