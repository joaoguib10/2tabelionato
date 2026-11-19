import re
import unicodedata
import uuid
from difflib import SequenceMatcher

from sqlalchemy import and_, case, func, literal, literal_column, or_
from sqlalchemy.orm import Session

from app.models import (
    ConsultaHistorico,
    ConsultaRevisao,
    Documento,
    DocumentoChunk,
    IAExternaFonte,
    Usuario,
)
from app.search_text import texto_metadados_documento_sql, tsvector_portugues_sql
from app.services.document_eligibility import condicoes_consulta

MAX_CHUNKS_ENTENDIMENTOS = 500
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
    "DISSOLUCAO_UNIAO_ESTAVEL": {"dissolucao", "uniao", "estavel"},
}

# Equivalências terminológicas usadas pela legislação quando a pergunta traz
# palavras cotidianas. A expansão é temática e não direciona a um artigo fixo.
EXPANSAO_BUSCA_TEMATICA = {
    "DOACAO": (
        "doação doador donatário liberalidade ascendente descendente filho "
        "herdeiro herança legítima colação disponível anuência consentimento venda"
    ),
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


def _tokens_com_termos_preservados(texto: str, preservar: set[str]) -> set[str]:
    tokens = _tokens(texto)
    for token in re.findall(r"\b[\w]+\b", _normalizar(texto)):
        token = token[:-1] if token.endswith("s") else token
        if token in preservar:
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
    termos_especificos = {
        termo
        for termo in termos_consulta - aliases_tema
        if not _termo_parece_erro_de_termo_generico(termo)
    }
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


def _termo_parece_erro_de_termo_generico(termo: str) -> bool:
    """Ignora erro ortográfico próximo de palavra funcional conhecida.

    Isso permite recuperar um entendimento pelo ato corretamente identificado
    sem deixar que um typo em palavras como ``escritura`` descarte a fonte.
    Termos jurídicos específicos continuam exigindo correspondência exata.
    """
    if len(termo) < 6:
        return False
    return any(
        len(palavra) >= 6
        and abs(len(termo) - len(palavra)) <= 2
        and SequenceMatcher(None, termo, palavra).ratio() >= 0.84
        for palavra in PALAVRAS_IGNORADAS
    )


def _padrao_termo_sql(termo: str) -> str:
    escapado = termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escapado}%"


def _termos_sqlite(consulta: str) -> list[str]:
    """Mantém acentos no fallback SQLite, cujo LIKE não aplica unaccent."""
    termos = set()
    for termo_original in re.findall(r"\b[\w]+\b", consulta.casefold()):
        termo_normalizado = _normalizar(termo_original)
        if len(termo_normalizado) >= 3 and termo_normalizado not in PALAVRAS_IGNORADAS:
            termos.add(termo_original)
    return sorted(termos)


def _termos_expandidos_por_tema(tema: str | None, postgresql: bool) -> set[str]:
    texto = EXPANSAO_BUSCA_TEMATICA.get(tema or "")
    if not texto:
        return set()
    termos = _tokens(texto) if postgresql else _termos_sqlite(texto)
    return set(termos)


def _filtro_candidatos_entendimento(
    consulta: str,
    db: Session,
    preservar_termos: set[str] | None = None,
):
    """Restringe a seleção no banco às palavras relevantes da pergunta.

    Em PostgreSQL usa o índice GIN existente de busca textual, com stemming
    português e correspondência OR para tolerar perguntas em linguagem natural.
    O caminho de outros dialetos preserva a suíte SQLite e o comportamento local.
    """
    postgresql = db.get_bind().dialect.name == "postgresql"
    termos = set(_tokens(consulta) if postgresql else _termos_sqlite(consulta))
    termos.update(_termos_expandidos_por_tema(_tema(consulta), postgresql))
    if preservar_termos:
        for termo in re.findall(r"\b[\w]+\b", consulta.casefold()):
            normalizado = _normalizar(termo)
            if normalizado in preservar_termos:
                termos.add(normalizado if postgresql else termo)
    termos = sorted(termos)
    if not termos:
        return None, literal(0.0)

    if postgresql:
        vetor = tsvector_portugues_sql(DocumentoChunk.conteudo)
        vetor_metadados = tsvector_portugues_sql(
            texto_metadados_documento_sql(
                Documento.titulo,
                Documento.descricao,
            )
        )
        consultas = [
            func.plainto_tsquery(literal_column("'portuguese'"), termo)
            for termo in termos
        ]
        consulta_fts = consultas[0]
        for consulta_termo in consultas[1:]:
            # tsquery || tsquery representa OR. Compor a consulta uma vez
            # evita recalcular to_tsvector para cada termo da pergunta em
            # milhares de chunks durante o filtro e o ranqueamento.
            consulta_fts = consulta_fts.op("||")(consulta_termo)
        correspondencia = or_(
            vetor.op("@@")(consulta_fts),
            vetor_metadados.op("@@")(consulta_fts),
        )
        relevancia = (
            func.ts_rank_cd(vetor, consulta_fts)
            + func.ts_rank_cd(vetor_metadados, consulta_fts) * 1.5
        )
        if _tema(consulta) == "DOACAO":
            # A lei descreve esse instituto como doação entre ascendentes e
            # descendentes; a pergunta cotidiana pode mencionar apenas pai e
            # filhos. O par conceitual eleva dispositivos que tratam dessa
            # relação sem amarrar a pesquisa a um número de artigo.
            consulta_parentesco = func.plainto_tsquery(
                literal_column("'portuguese'"), "ascendente descendente"
            )
            relevancia += (
                func.ts_rank_cd(vetor, consulta_parentesco)
                + func.ts_rank_cd(vetor_metadados, consulta_parentesco) * 1.5
            ) * 3.0
        return correspondencia, relevancia

    padroes = [_padrao_termo_sql(termo) for termo in termos]
    correspondencias_sqlite = [
        campo.ilike(padrao, escape="\\")
        for campo in (DocumentoChunk.conteudo, Documento.titulo, Documento.descricao)
        for padrao in padroes
    ]
    relevancia = sum(
        (
            case((DocumentoChunk.conteudo.ilike(padrao, escape="\\"), 1), else_=0)
            for padrao in padroes
        ),
        start=literal(0),
    )
    return or_(*correspondencias_sqlite), relevancia


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
    """Busca por palavras da pergunta e retorna o entendimento mais pertinente."""
    filtro_termos, relevancia_textual = _filtro_candidatos_entendimento(consulta, db)
    if filtro_termos is None:
        return []

    consulta_db = (
        db.query(DocumentoChunk, Documento)
        .join(Documento, Documento.id == DocumentoChunk.documento_id)
        .filter(
            *condicoes_consulta(),
            Documento.tipo == "ENTENDIMENTO",
            filtro_termos,
        )
    )
    if db.get_bind().dialect.name == "postgresql":
        consulta_db = consulta_db.order_by(
            relevancia_textual.desc(),
            Documento.aprovado_em.desc(),
            Documento.created_at.desc(),
        )
    else:
        consulta_db = consulta_db.order_by(
            Documento.aprovado_em.desc(), Documento.created_at.desc()
        )
    linhas = consulta_db.limit(MAX_CHUNKS_ENTENDIMENTOS).all()

    ranqueados = []
    tema_consulta = _tema(consulta)
    for chunk, documento in linhas:
        tema_titulo = _tema(documento.titulo)
        if tema_consulta and tema_titulo and tema_consulta != tema_titulo:
            continue

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
    postgres = db.get_bind().dialect.name == "postgresql"
    termos = sorted(_tokens(consulta)) if postgres else _termos_sqlite(consulta)
    if not termos:
        return []
    filtros_termos = or_(
        *(
            campo.ilike(_padrao_termo_sql(termo), escape="\\")
            for termo in termos
            for campo in (ConsultaHistorico.pergunta, ConsultaRevisao.resposta_humana)
        )
    )
    linhas = (
        db.query(ConsultaRevisao, ConsultaHistorico.pergunta)
        .join(ConsultaHistorico, ConsultaHistorico.id == ConsultaRevisao.consulta_id)
        .join(Usuario, Usuario.id == ConsultaRevisao.respondido_por)
        .filter(
            ConsultaRevisao.status.in_({"RESPONDIDA", "ENCERRADA"}),
            ConsultaRevisao.resposta_humana.is_not(None),
            ConsultaRevisao.entendimento_documento_id.is_(None),
            Usuario.role == "ADMIN",
            filtros_termos,
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


def buscar_documentos_institucionais_publicos(
    db: Session,
    consulta: str,
    limite: int = 6,
) -> list[dict]:
    """Recupera trechos locais cuja versão está liberada e indexada externamente.

    A busca textual usa o índice PostgreSQL já mantido para os chunks. O Gemini
    recebe apenas estes trechos aprovados para sintetizar a resposta; não recebe
    acesso ao banco nem aos anexos privados de Análise.
    """
    preservar = {"escritura", "publica", "publico"}
    filtro_termos, relevancia_textual = _filtro_candidatos_entendimento(
        consulta,
        db,
        preservar_termos=preservar,
    )
    if filtro_termos is None or limite <= 0:
        return []

    # Ampliar os candidatos antes do ranqueamento final evita que documentos
    # extensos, como códigos, escondam um trecho juridicamente equivalente.
    linhas = (
        db.query(
            DocumentoChunk,
            Documento,
            relevancia_textual.label("relevancia_textual"),
        )
        .join(Documento, Documento.id == DocumentoChunk.documento_id)
        .join(
            IAExternaFonte,
            and_(
                IAExternaFonte.documento_id == Documento.id,
                IAExternaFonte.pagina == DocumentoChunk.pagina,
                IAExternaFonte.escopo == "INSTITUCIONAL",
                IAExternaFonte.tipo_fonte == "DOCUMENTO",
                IAExternaFonte.tier.in_({"DOCUMENTOS", "ENTENDIMENTO"}),
                IAExternaFonte.status == "INDEXADO",
                IAExternaFonte.classificacao.in_({"PUBLICO", "SINTETICO"}),
            ),
        )
        .filter(*condicoes_consulta(), filtro_termos)
        .order_by(
            relevancia_textual.desc(),
            Documento.aprovado_em.desc(),
            Documento.created_at.desc(),
            DocumentoChunk.pagina.asc(),
            DocumentoChunk.posicao.asc(),
        )
        .limit(max(limite * 80, 400))
        .all()
    )

    consulta_tokens = _tokens_com_termos_preservados(consulta, preservar)
    tema_consulta = _tema(consulta)
    texto_expansao = EXPANSAO_BUSCA_TEMATICA.get(tema_consulta or "", "")
    termos_expandidos = _tokens(texto_expansao)
    ranqueados: list[
        tuple[float, float, float, float, DocumentoChunk, Documento]
    ] = []
    adicionados: set[str] = set()
    for chunk, documento, rank in linhas:
        chave = str(chunk.id)
        if chave in adicionados:
            continue
        adicionados.add(chave)
        texto = " ".join(
            item for item in (documento.titulo, documento.descricao, chunk.conteudo) if item
        )
        termos_texto = _tokens_com_termos_preservados(texto, preservar)
        cobertura = (
            len(consulta_tokens & termos_texto) / len(consulta_tokens)
            if consulta_tokens
            else 0.0
        )
        if cobertura <= 0:
            continue
        cobertura_tematica = (
            len(termos_expandidos & termos_texto) / len(termos_expandidos)
            if termos_expandidos
            else 0.0
        )
        termos_tema = consulta_tokens - preservar
        if not termos_tema:
            termos_tema = consulta_tokens
        termos_titulo = _tokens_com_termos_preservados(
            documento.titulo or "", preservar
        )
        correspondencia_titulo = (
            len(termos_tema & termos_titulo) / len(termos_tema)
            if termos_tema
            else 0.0
        )
        # Um título que corresponda ao tema da pergunta é um sinal útil para
        # localizar checklists e entendimentos específicos. A norma continua
        # recebendo preferência moderada, sem ocupar automaticamente as vagas.
        prioridade_norma = 0.08 if documento.tipo in {"NORMA", "LEGISLACAO"} else 0.0
        ranqueados.append(
            (
                correspondencia_titulo,
                cobertura_tematica,
                cobertura + prioridade_norma,
                float(rank or 0.0),
                chunk,
                documento,
            )
        )

    ranqueados.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
    if not ranqueados:
        return []

    selecionados: dict[str, tuple[DocumentoChunk, Documento, float]] = {}
    documentos_candidatos = {str(item[5].id) for item in ranqueados}
    limite_por_documento = (
        max(1, (limite + 1) // 2) if len(documentos_candidatos) > 1 else limite
    )
    contagem_por_documento: dict[str, int] = {}
    principais: list[tuple[DocumentoChunk, Documento, float]] = []
    for _, _, score, _, chunk, documento in ranqueados:
        documento_id = str(documento.id)
        if contagem_por_documento.get(documento_id, 0) >= limite_por_documento:
            continue
        selecionados[str(chunk.id)] = (chunk, documento, min(score, 0.99))
        principais.append((chunk, documento, min(score, 0.99)))
        contagem_por_documento[documento_id] = (
            contagem_por_documento.get(documento_id, 0) + 1
        )
        if len(selecionados) >= limite:
            break

    # A extração divide artigos extensos em vários chunks. Inclua a continuação
    # imediata do artigo para que o modelo veja juntos requisito, prazo e exceções.
    for chunk, documento, score in principais:
        if not chunk.artigo:
            continue
        vizinhos = (
            db.query(DocumentoChunk)
            .filter(
                DocumentoChunk.documento_id == documento.id,
                DocumentoChunk.pagina == chunk.pagina,
                DocumentoChunk.artigo == chunk.artigo,
                DocumentoChunk.posicao.in_([chunk.posicao - 1, chunk.posicao + 1]),
            )
            .order_by(DocumentoChunk.posicao.asc())
            .all()
        )
        for vizinho in vizinhos:
            if len(selecionados) >= limite + 3:
                break
            selecionados.setdefault(str(vizinho.id), (vizinho, documento, score))

    natureza_por_tipo = {
        "NORMA": "Norma institucional",
        "LEGISLACAO": "Legislação",
        "ENTENDIMENTO": "Entendimento administrativo publicado",
        "PROCEDIMENTO": "Procedimento interno aprovado",
        "MANUAL": "Manual institucional aprovado",
    }
    resultados = []
    for chunk, documento, score in selecionados.values():
        resultado = _resultado_chunk(chunk, documento, score)
        resultado["natureza_fonte"] = natureza_por_tipo.get(
            documento.tipo,
            "Documento institucional aprovado",
        )
        resultados.append(resultado)

    revisoes_candidatas = buscar_respostas_revisadas_admin(
        db,
        consulta,
        limite=3,
    )
    ids_revisoes = [
        uuid.UUID(fonte["fonte_id"].removeprefix("FONTE-"))
        for fonte in revisoes_candidatas
    ]
    if ids_revisoes:
        revisoes_liberadas = {
            str(revisao_id)
            for (revisao_id,) in (
                db.query(IAExternaFonte.revisao_id)
                .filter(
                    IAExternaFonte.revisao_id.in_(ids_revisoes),
                    IAExternaFonte.escopo == "INSTITUCIONAL",
                    IAExternaFonte.tipo_fonte == "REVISAO",
                    IAExternaFonte.tier == "REVISAO",
                    IAExternaFonte.status == "INDEXADO",
                    IAExternaFonte.classificacao.in_({"PUBLICO", "SINTETICO"}),
                )
                .all()
            )
            if revisao_id is not None
        }
        resultados.extend(
            fonte
            for fonte in revisoes_candidatas
            if fonte["fonte_id"].removeprefix("FONTE-") in revisoes_liberadas
        )
    return resultados
