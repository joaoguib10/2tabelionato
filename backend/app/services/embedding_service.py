import hashlib
import json
import urllib.request
from collections import OrderedDict
from threading import Lock

from sqlalchemy.orm import Session

from app.config import (
    OLLAMA_BASE_URL,
    OLLAMA_EMBED_MODEL,
    OLLAMA_EMBED_NUM_GPU,
    OLLAMA_KEEP_ALIVE,
    RAG_QUERY_EMBEDDING_CACHE_SIZE,
)
from app.models import DocumentoChunk
from app.services.ollama_security import garantir_ollama_permitido

MODELO_EMBEDDING = OLLAMA_EMBED_MODEL
OLLAMA_EMBED_URL = f"{OLLAMA_BASE_URL}/api/embed"

DIMENSAO_EMBEDDING = 768
TAMANHO_LOTE = 20
_cache_consultas: OrderedDict[str, tuple[float, ...]] = OrderedDict()
_cache_lock = Lock()


def _chave_cache(texto: str) -> str:
    conteudo = f"{MODELO_EMBEDDING}\0{texto}".encode("utf-8")
    return hashlib.sha256(conteudo).hexdigest()


def limpar_cache_embeddings_consulta() -> None:
    with _cache_lock:
        _cache_consultas.clear()


def gerar_embedding(
    texto: str,
) -> list[float]:
    garantir_ollama_permitido()
    chave = _chave_cache(texto)
    if RAG_QUERY_EMBEDDING_CACHE_SIZE > 0:
        with _cache_lock:
            armazenado = _cache_consultas.get(chave)
            if armazenado is not None:
                _cache_consultas.move_to_end(chave)
                return list(armazenado)

    dados = {
        "model": MODELO_EMBEDDING,
        "input": texto,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"num_gpu": OLLAMA_EMBED_NUM_GPU},
    }

    requisicao = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=json.dumps(dados).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        requisicao,
        timeout=120,
    ) as resposta:
        resultado = json.loads(resposta.read().decode("utf-8"))

    embeddings = resultado.get("embeddings")

    if not embeddings:
        raise RuntimeError("O Ollama não retornou um embedding.")

    vetor = embeddings[0]

    if len(vetor) != DIMENSAO_EMBEDDING:
        raise RuntimeError("Dimensão inesperada do embedding: " f"{len(vetor)}.")

    if RAG_QUERY_EMBEDDING_CACHE_SIZE > 0:
        with _cache_lock:
            _cache_consultas[chave] = tuple(vetor)
            _cache_consultas.move_to_end(chave)
            while len(_cache_consultas) > RAG_QUERY_EMBEDDING_CACHE_SIZE:
                _cache_consultas.popitem(last=False)

    return vetor


def gerar_embeddings_lote(
    textos: list[str],
) -> list[list[float]]:
    if not textos:
        return []

    garantir_ollama_permitido()

    dados = {
        "model": MODELO_EMBEDDING,
        "input": textos,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"num_gpu": OLLAMA_EMBED_NUM_GPU},
    }

    requisicao = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=json.dumps(dados).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        requisicao,
        timeout=300,
    ) as resposta:
        resultado = json.loads(resposta.read().decode("utf-8"))

    embeddings = resultado.get("embeddings")

    if not embeddings:
        raise RuntimeError("O Ollama não retornou embeddings.")

    if len(embeddings) != len(textos):
        raise RuntimeError(
            "A quantidade de embeddings retornados "
            "não corresponde à quantidade de textos enviados."
        )

    for vetor in embeddings:
        if len(vetor) != DIMENSAO_EMBEDDING:
            raise RuntimeError("Dimensão inesperada do embedding: " f"{len(vetor)}.")

    return embeddings


def gerar_embeddings_documento(
    db: Session,
    documento_id,
    tamanho_lote: int = TAMANHO_LOTE,
    commit: bool = True,
) -> int:
    """Gera embeddings somente para os chunks de um documento."""
    chunks = (
        db.query(DocumentoChunk)
        .filter(DocumentoChunk.documento_id == documento_id)
        .order_by(
            DocumentoChunk.pagina.asc(),
            DocumentoChunk.posicao.asc(),
        )
        .all()
    )

    total = 0

    for inicio in range(0, len(chunks), tamanho_lote):
        lote = chunks[inicio : inicio + tamanho_lote]
        vetores = gerar_embeddings_lote([chunk.conteudo for chunk in lote])

        for chunk, vetor in zip(lote, vetores):
            chunk.embedding = vetor

        total += len(lote)

    if commit:
        db.commit()
    else:
        db.flush()

    return total
