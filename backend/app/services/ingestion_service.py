import logging
from pathlib import Path

from app.database import SessionLocal
from app.models import Documento, DocumentoChunk, DocumentoPagina, utc_now
from app.services.chunk_service import gerar_chunks_documento
from app.services.document_processor import extrair_documento
from app.services.document_security import inspecionar_conteudo
from app.services.embedding_service import gerar_embeddings_documento

logger = logging.getLogger(__name__)


def processar_documento(documento_id, forcar_ocr: bool = False) -> None:
    """Executa extração, chunking e embeddings com status persistido."""
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
        if total_chunks:
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
