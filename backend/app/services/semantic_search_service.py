import logging
import re
import unicodedata
from time import perf_counter

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.config import RAG_CONFIDENCE_THRESHOLD
from app.models import Documento, DocumentoChunk
from app.services.document_eligibility import condicoes_consulta
from app.services.embedding_service import gerar_embedding

logger = logging.getLogger(__name__)

PALAVRAS_IGNORADAS = {
    "a",
    "as",
    "o",
    "os",
    "um",
    "uma",
    "uns",
    "umas",
    "de",
    "da",
    "das",
    "do",
    "dos",
    "em",
    "na",
    "nas",
    "no",
    "nos",
    "por",
    "para",
    "com",
    "sem",
    "sobre",
    "e",
    "ou",
    "que",
    "se",
    "é",
    "ser",
    "são",
    "qual",
    "quais",
    "como",
    "quando",
    "onde",
    "há",
    "tem",
    "ter",
    "precisa",
    "preciso",
    "necessário",
    "necessária",
    "necessários",
    "necessárias",
}

EXPRESSAO_NUMERO_ARTIGO = r"\d+(?:\.\d+)*(?:\s*[º°o])?(?:-[a-z])?"
PADRAO_REFERENCIA_ARTIGO = re.compile(
    rf"(?i)(?<![\w])art(?:igo)?s?\.?\s*({EXPRESSAO_NUMERO_ARTIGO})"
)
PADRAO_LISTA_ARTIGOS = re.compile(
    rf"(?i)(?<![\w])art(?:igo)?s?\.?\s*"
    rf"(?P<lista>{EXPRESSAO_NUMERO_ARTIGO}"
    rf"(?:(?:\s*,\s*|\s*;\s*|\s+e\s+){EXPRESSAO_NUMERO_ARTIGO})*)"
)
PADRAO_NUMERO_ARTIGO = re.compile(EXPRESSAO_NUMERO_ARTIGO, re.IGNORECASE)


def _normalizar_numero_artigo(numero: str) -> str:
    normalizado = re.sub(r"\s+", "", numero).upper()
    return re.sub(r"(?<=\d)[°O](?=-[A-Z]$|$)", "º", normalizado)


def _numero_artigo_para_chave(numero: str) -> str:
    return _normalizar_numero_artigo(numero).replace("º", "")


def _chave_artigo(artigo: str | None) -> str | None:
    if not artigo:
        return None
    encontrado = PADRAO_REFERENCIA_ARTIGO.search(artigo)
    if not encontrado:
        return None
    return f"art.{_numero_artigo_para_chave(encontrado.group(1)).casefold()}"


def extrair_referencias_artigos(consulta: str) -> list[str]:
    """Extrai referências explícitas sem deduzir artigos pelo restante da pergunta."""
    referencias = []
    adicionadas: set[str] = set()
    for lista_encontrada in PADRAO_LISTA_ARTIGOS.finditer(consulta):
        for encontrado in PADRAO_NUMERO_ARTIGO.finditer(
            lista_encontrada.group("lista")
        ):
            numero = _normalizar_numero_artigo(encontrado.group(0))
            chave = _numero_artigo_para_chave(numero).casefold()
            if chave in adicionadas:
                continue
            referencias.append(f"Art. {numero}")
            adicionadas.add(chave)
    return referencias


def normalizar_termo(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto)
    return "".join(
        caractere for caractere in texto if unicodedata.category(caractere) != "Mn"
    ).casefold()


def extrair_termos_importantes(consulta: str) -> list[str]:
    termos = re.findall(r"\b[\w]+\b", normalizar_termo(consulta), flags=re.UNICODE)
    return [
        termo for termo in termos if len(termo) >= 3 and termo not in PALAVRAS_IGNORADAS
    ]


def calcular_relevancia_termos(consulta: str, conteudo: str) -> float:
    termos = extrair_termos_importantes(consulta)
    if not termos:
        return 0.0
    conteudo_normalizado = normalizar_termo(conteudo)
    encontrados = sum(
        1
        for termo in termos
        if re.search(rf"\b{re.escape(termo)}\b", conteudo_normalizado)
    )
    return encontrados / len(termos)


def calcular_bonus_frase(consulta: str, conteudo: str) -> float:
    termos = extrair_termos_importantes(consulta)
    if len(termos) < 2:
        return 0.0
    frases = [
        " ".join(termos[inicio : inicio + tamanho])
        for tamanho in (2, 3)
        for inicio in range(len(termos) - tamanho + 1)
    ]
    conteudo_normalizado = normalizar_termo(conteudo)
    return sum(frase in conteudo_normalizado for frase in frases) / len(frases)


def calcular_pontuacao_hibrida(
    consulta: str,
    conteudo: str,
    similaridade_semantica: float,
    relevancia_textual: float,
    bonus_rrf: float,
) -> float:
    cobertura = calcular_relevancia_termos(consulta, conteudo)
    frase = calcular_bonus_frase(consulta, conteudo)
    semantica = max(0.0, min(1.0, similaridade_semantica))
    textual = max(0.0, relevancia_textual)
    textual_normalizada = textual / (textual + 0.1) if textual else 0.0
    return max(
        0.0,
        min(
            1.0,
            (semantica * 0.48)
            + (textual_normalizada * 0.22)
            + (cobertura * 0.20)
            + (frase * 0.05)
            + (bonus_rrf * 0.05),
        ),
    )


def _fonte_id(chunk: DocumentoChunk) -> str:
    return f"FONTE-{chunk.id}"


def _resultado(
    chunk: DocumentoChunk,
    titulo: str,
    versao: str | None,
    pontuacao: float,
) -> dict:
    pagina_confiavel = getattr(chunk, "pagina_confiavel", True) is not False
    artigo_confirmado = getattr(chunk, "artigo_confirmado", False) is True
    return {
        "fonte_id": _fonte_id(chunk),
        "chunk_id": str(chunk.id),
        "documento_id": str(chunk.documento_id),
        "documento": titulo,
        "versao_documento": versao,
        "pagina": chunk.pagina if pagina_confiavel else None,
        "localizacao": getattr(chunk, "localizacao", None),
        "posicao": chunk.posicao,
        "artigo": chunk.artigo if artigo_confirmado else None,
        "capitulo": getattr(chunk, "capitulo", None),
        "secao": getattr(chunk, "secao", None),
        "paragrafo": getattr(chunk, "paragrafo", None),
        "inciso": getattr(chunk, "inciso", None),
        "conteudo": chunk.conteudo,
        "similaridade": round(pontuacao, 4),
    }


def _expressao_chave_artigo():
    sem_espacos = func.lower(func.replace(DocumentoChunk.artigo, " ", ""))
    sem_ordinais = func.replace(func.replace(sem_espacos, "º", ""), "°", "")
    return sem_ordinais


def _pontuacao_pista_titulo(consulta: str, titulo: str) -> float:
    """Prioriza pistas textuais sem eliminar documentos com artigo homônimo."""
    consulta_normalizada = normalizar_termo(consulta)
    titulo_normalizado = normalizar_termo(titulo).strip()
    termos_titulo = set(extrair_termos_importantes(titulo))
    termos_consulta = set(extrair_termos_importantes(consulta))
    cobertura = (
        len(termos_titulo & termos_consulta) / len(termos_titulo)
        if termos_titulo
        else 0.0
    )
    correspondencia_exata = bool(
        titulo_normalizado and titulo_normalizado in consulta_normalizada
    )
    return cobertura + (2.0 if correspondencia_exata else 0.0)


def _buscar_chunks_por_artigos(
    db: Session,
    referencias: list[str],
    limite: int,
    consulta: str = "",
) -> list[dict]:
    """Busca artigos confirmados e distribui o contexto entre documentos ambíguos.

    Um valor de ``artigo`` herdado pelo chunking só pode participar depois que o
    mesmo documento possuir uma âncora confirmada para o artigo. A continuação é
    recuperada para completar a regra, mas `_resultado` não exibe nela o artigo
    herdado como se estivesse escrito no próprio trecho.
    """
    chaves_referencias = [
        chave
        for referencia in referencias
        if (chave := _chave_artigo(referencia)) is not None
    ]
    if not chaves_referencias or limite <= 0:
        return []

    chave_sql = _expressao_chave_artigo()
    ancoras = (
        db.query(
            DocumentoChunk,
            Documento.titulo.label("documento_titulo"),
            Documento.versao.label("documento_versao"),
        )
        .join(Documento, Documento.id == DocumentoChunk.documento_id)
        .filter(
            *condicoes_consulta(),
            DocumentoChunk.artigo_confirmado.is_(True),
            chave_sql.in_(chaves_referencias),
        )
        .order_by(
            Documento.titulo.asc(),
            DocumentoChunk.pagina.asc(),
            DocumentoChunk.posicao.asc(),
        )
        .all()
    )

    grupos_encontrados: dict[tuple[str, str], dict] = {}
    for linha in ancoras:
        chunk = linha.DocumentoChunk
        chave_artigo = _chave_artigo(chunk.artigo)
        if chave_artigo not in chaves_referencias:
            continue
        chave_grupo = (str(chunk.documento_id), chave_artigo)
        if chave_grupo in grupos_encontrados:
            continue
        grupos_encontrados[chave_grupo] = {
            "documento_id": chunk.documento_id,
            "artigo": chave_artigo,
            "documento": linha.documento_titulo,
            "versao": getattr(linha, "documento_versao", None),
            "prioridade_titulo": _pontuacao_pista_titulo(
                consulta,
                linha.documento_titulo,
            ),
        }

    if not grupos_encontrados:
        return []

    grupos_por_artigo = {chave: [] for chave in chaves_referencias}
    for chave_grupo, info in grupos_encontrados.items():
        grupos_por_artigo[info["artigo"]].append((chave_grupo, info))
    for grupos_artigo in grupos_por_artigo.values():
        grupos_artigo.sort(
            key=lambda item: (
                -item[1]["prioridade_titulo"],
                normalizar_termo(item[1]["documento"]),
                str(item[1]["documento_id"]),
            )
        )

    grupos_selecionados: dict[tuple[str, str], dict] = {}
    indice = 0
    # Distribui as vagas também entre números de artigo diferentes. Sem esse
    # rodízio, muitos documentos com o primeiro número poderiam ocultar uma
    # segunda referência explícita da mesma pergunta.
    while len(grupos_selecionados) < limite:
        adicionou = False
        for chave_artigo in chaves_referencias:
            grupos_artigo = grupos_por_artigo[chave_artigo]
            if indice >= len(grupos_artigo):
                continue
            chave_grupo, info = grupos_artigo[indice]
            grupos_selecionados[chave_grupo] = info
            adicionou = True
            if len(grupos_selecionados) >= limite:
                break
        if not adicionou:
            break
        indice += 1

    condicoes_grupos = [
        and_(
            DocumentoChunk.documento_id == grupo["documento_id"],
            chave_sql == grupo["artigo"],
        )
        for grupo in grupos_selecionados.values()
    ]
    linhas = (
        db.query(
            DocumentoChunk,
            Documento.titulo.label("documento_titulo"),
            Documento.versao.label("documento_versao"),
        )
        .join(Documento, Documento.id == DocumentoChunk.documento_id)
        .filter(*condicoes_consulta(), or_(*condicoes_grupos))
        .order_by(
            Documento.titulo.asc(),
            DocumentoChunk.pagina.asc(),
            DocumentoChunk.posicao.asc(),
        )
        .all()
    )

    grupos: dict[tuple[str, str], list] = {chave: [] for chave in grupos_selecionados}
    for linha in linhas:
        chunk = linha.DocumentoChunk
        chave_grupo = (str(chunk.documento_id), _chave_artigo(chunk.artigo))
        if chave_grupo in grupos:
            grupos[chave_grupo].append(linha)

    ordem_artigos = {chave: posicao for posicao, chave in enumerate(chaves_referencias)}
    grupos_ordenados: list[tuple[dict, list]] = []
    for chave_grupo, linhas_grupo in grupos.items():
        linhas_grupo.sort(
            key=lambda linha: (
                linha.DocumentoChunk.pagina,
                linha.DocumentoChunk.posicao,
            )
        )
        primeira_ancora = next(
            (
                indice
                for indice, linha in enumerate(linhas_grupo)
                if getattr(linha.DocumentoChunk, "artigo_confirmado", False) is True
            ),
            None,
        )
        if primeira_ancora is None:
            continue
        info = grupos_selecionados[chave_grupo]
        grupos_ordenados.append((info, linhas_grupo[primeira_ancora:]))

    grupos_ordenados.sort(
        key=lambda item: (
            ordem_artigos.get(item[0]["artigo"], len(ordem_artigos)),
            -item[0]["prioridade_titulo"],
            normalizar_termo(item[0]["documento"]),
            str(item[0]["documento_id"]),
        )
    )

    resultados = []
    profundidade = 0
    # Rodízio: primeiro retorna a âncora de cada documento; somente depois
    # acrescenta continuações. Assim artigos homônimos permanecem ambíguos.
    while len(resultados) < limite:
        adicionou = False
        for info, linhas_grupo in grupos_ordenados:
            if profundidade >= len(linhas_grupo):
                continue
            linha = linhas_grupo[profundidade]
            resultados.append(
                _resultado(
                    linha.DocumentoChunk,
                    info["documento"],
                    info["versao"],
                    max(0.85, 1.0 - (profundidade * 0.02)),
                )
            )
            adicionou = True
            if len(resultados) >= limite:
                break
        if not adicionou:
            break
        profundidade += 1
    return resultados


def _buscar_vizinhos(db: Session, chunk: DocumentoChunk) -> list[DocumentoChunk]:
    anterior = (
        db.query(DocumentoChunk)
        .filter(
            DocumentoChunk.documento_id == chunk.documento_id,
            or_(
                DocumentoChunk.pagina < chunk.pagina,
                and_(
                    DocumentoChunk.pagina == chunk.pagina,
                    DocumentoChunk.posicao < chunk.posicao,
                ),
            ),
        )
        .order_by(DocumentoChunk.pagina.desc(), DocumentoChunk.posicao.desc())
        .first()
    )
    proximo = (
        db.query(DocumentoChunk)
        .filter(
            DocumentoChunk.documento_id == chunk.documento_id,
            or_(
                DocumentoChunk.pagina > chunk.pagina,
                and_(
                    DocumentoChunk.pagina == chunk.pagina,
                    DocumentoChunk.posicao > chunk.posicao,
                ),
            ),
        )
        .order_by(DocumentoChunk.pagina.asc(), DocumentoChunk.posicao.asc())
        .first()
    )
    return [item for item in (anterior, proximo) if item is not None]


def buscar_chunks_semelhantes(
    db: Session,
    consulta: str,
    limite: int = 8,
    limiar: float | None = None,
) -> list[dict]:
    """Une busca por artigo, candidatos híbridos, governança e contexto seguro."""
    inicio_total = perf_counter()
    limiar_efetivo = RAG_CONFIDENCE_THRESHOLD if limiar is None else limiar
    limite_candidatos = max(30, limite * 4)
    referencias_artigos = extrair_referencias_artigos(consulta)
    inicio_artigos = perf_counter()
    resultados_artigos = _buscar_chunks_por_artigos(
        db,
        referencias_artigos,
        limite,
        consulta=consulta,
    )
    tempo_artigos = perf_counter() - inicio_artigos
    # Uma correspondência confirmada na metadata é mais específica do que os
    # embeddings para perguntas que nomeiam um artigo. Esse retorno também
    # mantém a busca direta disponível se o serviço de embeddings estiver
    # temporariamente indisponível.
    if resultados_artigos:
        logger.info(
            "RAG busca concluída: modo=artigo artigos=%s fontes=%s "
            "artigos_ms=%.1f total_ms=%.1f",
            len(referencias_artigos),
            len(resultados_artigos),
            tempo_artigos * 1000,
            (perf_counter() - inicio_total) * 1000,
        )
        return resultados_artigos

    tempo_corpus = 0.0
    if isinstance(db, Session):
        inicio_corpus = perf_counter()
        possui_corpus = (
            db.query(DocumentoChunk.id)
            .join(Documento, Documento.id == DocumentoChunk.documento_id)
            .filter(
                *condicoes_consulta(),
                DocumentoChunk.embedding.is_not(None),
            )
            .first()
        )
        tempo_corpus = perf_counter() - inicio_corpus
        if possui_corpus is None:
            logger.info(
                "RAG busca concluída: modo=hibrido corpus=0 artigos_ms=%.1f "
                "corpus_ms=%.1f total_ms=%.1f",
                tempo_artigos * 1000,
                tempo_corpus * 1000,
                (perf_counter() - inicio_total) * 1000,
            )
            return []

    inicio_embedding = perf_counter()
    vetor_consulta = gerar_embedding(consulta)
    tempo_embedding = perf_counter() - inicio_embedding
    distancia = DocumentoChunk.embedding.cosine_distance(vetor_consulta)
    similaridade = 1 - distancia

    base = (
        db.query(
            DocumentoChunk,
            Documento.titulo.label("documento_titulo"),
            Documento.versao.label("documento_versao"),
            similaridade.label("similaridade_semantica"),
        )
        .join(Documento, Documento.id == DocumentoChunk.documento_id)
        .filter(*condicoes_consulta(), DocumentoChunk.embedding.is_not(None))
    )
    inicio_semantica = perf_counter()
    # Ordenar pela distância direta permite ao PostgreSQL usar o índice HNSW
    # vector_cosine_ops. A similaridade continua sendo calculada para o reranking.
    semanticos = base.order_by(distancia.asc()).limit(limite_candidatos).all()
    tempo_semantica = perf_counter() - inicio_semantica

    vetor_textual = func.to_tsvector("portuguese", DocumentoChunk.conteudo)
    query_textual = func.plainto_tsquery("portuguese", consulta)
    rank_textual = func.ts_rank_cd(vetor_textual, query_textual)
    inicio_textual = perf_counter()
    textuais = (
        db.query(
            DocumentoChunk,
            Documento.titulo.label("documento_titulo"),
            Documento.versao.label("documento_versao"),
            rank_textual.label("relevancia_textual"),
            similaridade.label("similaridade_semantica"),
        )
        .join(Documento, Documento.id == DocumentoChunk.documento_id)
        .filter(
            *condicoes_consulta(),
            DocumentoChunk.embedding.is_not(None),
            vetor_textual.op("@@")(query_textual),
        )
        .order_by(rank_textual.desc())
        .limit(limite_candidatos)
        .all()
    )
    tempo_textual = perf_counter() - inicio_textual

    candidatos: dict[str, dict] = {}
    for posicao, linha in enumerate(semanticos, start=1):
        chunk = linha.DocumentoChunk
        candidatos[str(chunk.id)] = {
            "chunk": chunk,
            "documento": linha.documento_titulo,
            "versao": getattr(linha, "documento_versao", None),
            "semantica": float(linha.similaridade_semantica),
            "textual": 0.0,
            "rrf": 1 / (60 + posicao),
        }
    for posicao, linha in enumerate(textuais, start=1):
        chunk = linha.DocumentoChunk
        candidato = candidatos.setdefault(
            str(chunk.id),
            {
                "chunk": chunk,
                "documento": linha.documento_titulo,
                "versao": getattr(linha, "documento_versao", None),
                "semantica": 0.0,
                "textual": 0.0,
                "rrf": 0.0,
            },
        )
        candidato["textual"] = float(linha.relevancia_textual)
        candidato["semantica"] = max(
            candidato["semantica"], float(linha.similaridade_semantica)
        )
        candidato["rrf"] += 1 / (60 + posicao)

    maior_rrf = max((item["rrf"] for item in candidatos.values()), default=1.0)
    ranqueados = []
    for candidato in candidatos.values():
        chunk = candidato["chunk"]
        pontuacao = calcular_pontuacao_hibrida(
            consulta,
            chunk.conteudo,
            candidato["semantica"],
            candidato["textual"],
            candidato["rrf"] / maior_rrf,
        )
        if pontuacao >= limiar_efetivo:
            ranqueados.append((pontuacao, candidato))
    ranqueados.sort(key=lambda item: item[0], reverse=True)

    resultados = []
    adicionados: set[str] = set()
    for pontuacao, candidato in ranqueados:
        if len(resultados) >= limite:
            break
        chunk = candidato["chunk"]
        chave = str(chunk.id)
        if chave not in adicionados:
            resultados.append(
                _resultado(
                    chunk, candidato["documento"], candidato["versao"], pontuacao
                )
            )
            adicionados.add(chave)
        if len(resultados) >= limite:
            break

        if isinstance(db, Session) and not referencias_artigos:
            for vizinho in _buscar_vizinhos(db, chunk):
                chave_vizinho = str(vizinho.id)
                if chave_vizinho in adicionados:
                    continue
                resultados.append(
                    _resultado(
                        vizinho,
                        candidato["documento"],
                        candidato["versao"],
                        max(limiar_efetivo, pontuacao * 0.9),
                    )
                )
                adicionados.add(chave_vizinho)
                if len(resultados) >= limite:
                    break
        if len(resultados) >= limite:
            break
    logger.info(
        "RAG busca concluída: modo=hibrido artigos_ms=%.1f corpus_ms=%.1f "
        "embedding_ms=%.1f semantica_ms=%.1f textual_ms=%.1f "
        "candidatos=%s fontes=%s total_ms=%.1f",
        tempo_artigos * 1000,
        tempo_corpus * 1000,
        tempo_embedding * 1000,
        tempo_semantica * 1000,
        tempo_textual * 1000,
        len(candidatos),
        len(resultados),
        (perf_counter() - inicio_total) * 1000,
    )
    return resultados
