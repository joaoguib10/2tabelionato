import re

from sqlalchemy.orm import Session

from app.models import DocumentoChunk, DocumentoPagina
from app.services.chunking import dividir_texto

EXPRESSAO_NUMERO_ARTIGO = r"\d+(?:\.\d+)*(?:\s*[º°o])?(?:-[A-Z])?"
PADRAO_ARTIGO = re.compile(
    rf"(?im)^\s*(?:Art(?:igo)?\.?)\s*({EXPRESSAO_NUMERO_ARTIGO})" r"(?=\s|[.,;:–—-]|$)"
)
PADRAO_CAPITULO = re.compile(r"(?im)^\s*(CAP[IÍ]TULO\s+[IVXLCDM\d]+[^\n]*)")
PADRAO_SECAO = re.compile(r"(?im)^\s*((?:SE[CÇ][AÃ]O|SUBSE[CÇ][AÃ]O)\s+[^\n]+)")
PADRAO_PARAGRAFO = re.compile(r"(?im)^\s*((?:§\s*\d+[ºo]?|Parágrafo\s+único))\b")
PADRAO_INCISO = re.compile(r"(?im)^\s*([IVXLCDM]+\s*[-–—])")


def _primeira_ocorrencia(
    padrao: re.Pattern,
    texto: str,
    limite: int | None = None,
) -> str | None:
    ocorrencia = padrao.search(texto)
    if not ocorrencia:
        return None
    valor = ocorrencia.group(1).strip()
    return valor[:limite] if limite else valor


def extrair_artigo(texto: str) -> str | None:
    ocorrencia = PADRAO_ARTIGO.search(texto)
    if not ocorrencia:
        return None
    numero = re.sub(r"\s+", "", ocorrencia.group(1)).upper()
    numero = re.sub(r"(?<=\d)[°O](?=-[A-Z]$|$)", "º", numero)
    return f"Art. {numero}"[:50]


def gerar_chunks_documento(
    db: Session,
    documento_id,
    commit: bool = True,
) -> int:
    paginas = (
        db.query(DocumentoPagina)
        .filter(DocumentoPagina.documento_id == documento_id)
        .order_by(DocumentoPagina.pagina.asc())
        .all()
    )
    if not paginas:
        raise ValueError("O documento não possui páginas processadas.")

    db.query(DocumentoChunk).filter(DocumentoChunk.documento_id == documento_id).delete(
        synchronize_session=False
    )

    total_chunks = 0
    artigo_atual = None
    capitulo_atual = None
    secao_atual = None

    for pagina in paginas:
        chunks = dividir_texto(pagina.conteudo)
        for posicao, conteudo in enumerate(chunks, start=1):
            artigo_encontrado = extrair_artigo(conteudo)
            capitulo_encontrado = _primeira_ocorrencia(PADRAO_CAPITULO, conteudo, 200)
            secao_encontrada = _primeira_ocorrencia(PADRAO_SECAO, conteudo, 200)

            if artigo_encontrado:
                artigo_atual = artigo_encontrado
            if capitulo_encontrado:
                capitulo_atual = capitulo_encontrado
            if secao_encontrada:
                secao_atual = secao_encontrada

            if pagina.pagina_confiavel:
                localizacao = pagina.localizacao or f"Página {pagina.pagina}"
            else:
                localizacao = (
                    f"{pagina.localizacao or f'Bloco lógico {pagina.pagina}'}"
                    f" · trecho {posicao}"
                )

            db.add(
                DocumentoChunk(
                    documento_id=documento_id,
                    pagina=pagina.pagina,
                    posicao=posicao,
                    artigo=artigo_atual,
                    artigo_confirmado=artigo_encontrado is not None,
                    capitulo=capitulo_atual,
                    secao=secao_atual,
                    paragrafo=_primeira_ocorrencia(PADRAO_PARAGRAFO, conteudo, 100),
                    inciso=_primeira_ocorrencia(PADRAO_INCISO, conteudo, 50),
                    pagina_confiavel=pagina.pagina_confiavel,
                    localizacao=localizacao,
                    conteudo=conteudo,
                )
            )
            total_chunks += 1

    if commit:
        db.commit()
    else:
        db.flush()
    return total_chunks
