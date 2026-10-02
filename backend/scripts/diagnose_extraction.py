"""Compara extração e índice sem gravar dados ou imprimir conteúdo documental."""

import argparse
import json
from uuid import UUID

from app.database import SessionLocal
from app.models import Documento, DocumentoChunk, DocumentoPagina
from app.services.chunking import dividir_texto
from app.services.document_processor import extrair_documento
from sqlalchemy import text


def diagnosticar(db, documento_id: UUID) -> dict:
    documento = db.get(Documento, documento_id)
    if documento is None:
        raise ValueError("Documento não encontrado.")
    resultado = extrair_documento(documento.caminho_arquivo, executar_ocr=False)
    paginas = db.query(DocumentoPagina).filter_by(documento_id=documento_id).all()
    chunks = db.query(DocumentoChunk).filter_by(documento_id=documento_id)
    return {
        "situacao_detectada": resultado.situacao,
        "extracao_atual": resultado.resumo(),
        "chunks_recalculados_em_memoria": sum(
            len(dividir_texto(p.conteudo)) for p in resultado.partes
        ),
        "banco": {
            "situacao_extracao": documento.situacao_extracao,
            "partes_armazenadas": len(paginas),
            "caracteres_armazenados": sum(len(p.conteudo) for p in paginas),
            "chunks_armazenados": chunks.count(),
            "chunks_com_embedding": chunks.filter(
                DocumentoChunk.embedding.is_not(None)
            ).count(),
            "contador_partes": documento.total_paginas,
            "contador_chunks": documento.total_chunks,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("documento_id", type=UUID)
    args = parser.parse_args()
    with SessionLocal() as db:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SET TRANSACTION READ ONLY"))
        try:
            print(
                json.dumps(
                    diagnosticar(db, args.documento_id), ensure_ascii=False, indent=2
                )
            )
        except Exception:
            raise SystemExit(
                "Não foi possível diagnosticar o documento. Confira o identificador, o formato e a disponibilidade do arquivo."
            ) from None
        finally:
            db.rollback()


if __name__ == "__main__":
    main()
