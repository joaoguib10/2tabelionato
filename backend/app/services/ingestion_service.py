import logging
from pathlib import Path

from app.config import (
    CONSULTA_ONLY_MODE,
    EXTERNAL_AI_ENABLED,
    EXTERNAL_AI_FREE_TIER_CONFIRMED,
    GEMINI_API_KEY,
)
from app.database import SessionLocal
from app.models import Documento, DocumentoChunk, DocumentoPagina, utc_now
from app.services.chunk_service import gerar_chunks_documento
from app.services.document_processor import EXTRACOES_COMPLETAS, extrair_documento
from app.services.document_eligibility import CATEGORIAS_CONSULTA, documento_elegivel_consulta
from app.services.document_security import inspecionar_conteudo
from app.services.embedding_service import gerar_embeddings_documento
from app.services.external_ai_service import liberar_documento_institucional

logger = logging.getLogger(__name__)


def processar_documento(documento_id, forcar_ocr: bool = False) -> None:
    """Executa extração e chunking; gera embeddings locais só quando necessários."""
    db = SessionLocal()

    try:
        documento = db.get(Documento, documento_id)

        if documento is None:
            logger.warning("Documento %s não encontrado para ingestão.", documento_id)
            return

        documento.status = "PROCESSANDO"
        documento.erro_processamento = None
        documento.processado_em = None
        db.commit()

        extracao = (
            extrair_documento(documento.caminho_arquivo, forcar_ocr=True)
            if forcar_ocr
            else extrair_documento(documento.caminho_arquivo)
        )
        paginas = [(p.numero, p.conteudo) for p in extracao.partes if p.conteudo]
        inspecao = inspecionar_conteudo(paginas)
        documento.status_seguranca = inspecao.status
        documento.alerta_seguranca = inspecao.alerta

        db.query(DocumentoChunk).filter(
            DocumentoChunk.documento_id == documento.id
        ).delete(synchronize_session=False)
        db.query(DocumentoPagina).filter(
            DocumentoPagina.documento_id == documento.id
        ).delete(synchronize_session=False)

        pagina_confiavel = Path(documento.nome_arquivo).suffix.lower() == ".pdf"
        for parte in extracao.partes:
            numero, conteudo = parte.numero, parte.conteudo
            db.add(
                DocumentoPagina(
                    documento_id=documento.id,
                    pagina=numero,
                    pagina_confiavel=pagina_confiavel,
                    localizacao=(
                        f"Página {numero}"
                        if pagina_confiavel
                        else f"Bloco lógico {numero}"
                    ),
                    conteudo=conteudo,
                    metodo_extracao=parte.metodo,
                    situacao_extracao=parte.situacao,
                )
            )

        db.flush()
        total_chunks = (
            gerar_chunks_documento(
                db,
                documento.id,
                commit=False,
            )
            if paginas
            else 0
        )
        usar_embeddings_locais = not (
            EXTERNAL_AI_ENABLED
            and EXTERNAL_AI_FREE_TIER_CONFIRMED
            and GEMINI_API_KEY
        )
        if total_chunks and not CONSULTA_ONLY_MODE and usar_embeddings_locais:
            gerar_embeddings_documento(
                db,
                documento.id,
                commit=False,
            )

        documento.total_paginas = len(extracao.partes)
        documento.total_chunks = total_chunks
        documento.situacao_extracao = extracao.situacao
        documento.diagnostico_extracao = extracao.resumo()
        documento.status = "PRONTO" if total_chunks else "ERRO"
        documento.erro_processamento = None
        documento.processado_em = utc_now()

        if (
            documento.tipo in CATEGORIAS_CONSULTA
            and documento.situacao == "RASCUNHO"
            and documento.status == "PRONTO"
            and documento.situacao_extracao in EXTRACOES_COMPLETAS
            and documento.status_seguranca == "LIBERADO"
            and documento.ativo
        ):
            documento.situacao = "APROVADO"
            documento.aprovado_por = documento.criado_por
            documento.aprovado_em = utc_now()

        if documento_elegivel_consulta(documento):
            try:
                liberar_documento_institucional(
                    db, documento, "PUBLICO", documento.aprovado_por or documento.criado_por,
                    confirmar_fonte_publica=True,
                )
            except ValueError as erro:
                logger.warning(
                    "Documento processado sem liberação externa; id=%s motivo=%s",
                    documento.id, erro,
                )
        db.commit()

    except Exception as erro:
        db.rollback()
        logger.error(
            "Falha na ingestão do documento %s (tipo=%s).",
            documento_id,
            type(erro).__name__,
        )

        documento = db.get(Documento, documento_id)
        if documento is not None:
            documento.status = "ERRO"
            documento.situacao_extracao = "ERRO_PROCESSAMENTO"
            if isinstance(erro, FileNotFoundError):
                mensagem = (
                    "O arquivo do documento não está disponível para processamento."
                )
            else:
                mensagem = "Falha interna durante o processamento. Tente reprocessar."
            documento.erro_processamento = mensagem[:500]
            documento.processado_em = utc_now()
            db.commit()

    finally:
        db.close()
