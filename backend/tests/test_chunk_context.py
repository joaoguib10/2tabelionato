from app.models import Documento, DocumentoChunk, DocumentoPagina
from app.services.chunk_service import gerar_chunks_documento
from app.services.document_processor import limpar_texto_extraido


def test_chunk_preserva_estrutura_e_nao_trata_docx_como_pagina_fisica(
    db,
    usuario_factory,
):
    usuario = usuario_factory("estrutura")
    documento = Documento(
        titulo="Manual estruturado",
        tipo="MANUAL",
        situacao="RASCUNHO",
        nome_arquivo="manual.docx",
        caminho_arquivo="arquivo-de-teste",
        criado_por=usuario.id,
        status="PROCESSANDO",
    )
    db.add(documento)
    db.flush()
    db.add(
        DocumentoPagina(
            documento_id=documento.id,
            pagina=1,
            pagina_confiavel=False,
            localizacao="Documento sem paginação física",
            conteudo=(
                "CAPÍTULO I - DISPOSIÇÕES\n\n"
                "SEÇÃO I - REGRAS\n\n"
                "Art. 10 A regra principal.\n\n"
                "§ 1º A exceção aplicável."
            ),
        )
    )
    db.commit()
    gerar_chunks_documento(db, documento.id)
    chunk = (
        db.query(DocumentoChunk)
        .filter_by(documento_id=documento.id, artigo="Art. 10")
        .first()
    )
    assert chunk is not None
    assert chunk.capitulo.startswith("CAPÍTULO I")
    assert chunk.secao.startswith("SEÇÃO I")
    assert chunk.artigo == "Art. 10"
    assert chunk.artigo_confirmado is True
    assert chunk.pagina_confiavel is False
    assert chunk.localizacao.endswith("trecho 2")
    assert "paginação física" in chunk.localizacao


def test_texto_extraido_remove_controles_incompativeis():
    assert limpar_texto_extraido("Art. 1\x00\x01\nTexto") == "Art. 1\nTexto"
