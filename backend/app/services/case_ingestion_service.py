import logging
from pathlib import Path
from threading import Lock
from uuid import UUID

from app.database import SessionLocal
from app.models import (
    CasoDocumento,
    CasoDocumentoPagina,
    utc_now,
)
from app.services.case_task_service import (
    concluir_tarefa,
    falhar_tarefa,
    iniciar_tarefa,
)
from app.services.document_processor import (
    extrair_documento,
)
from app.services.document_security import (
    inspecionar_conteudo,
)

logger = logging.getLogger(__name__)

# Piloto local: um único processo da API. Inclui tarefas ainda aguardando execução.
_reserva_lock = Lock()
_processamentos: set = set()


def reservar_processamento(caso_documento_id) -> bool:
    with _reserva_lock:
        if caso_documento_id in _processamentos:
            return False
        _processamentos.add(caso_documento_id)
        return True


def liberar_processamento(caso_documento_id) -> None:
    with _reserva_lock:
        _processamentos.discard(caso_documento_id)


def processar_documento_caso(
    caso_documento_id,
    forcar_ocr: bool = False,
    tarefa_id: UUID | None = None,
) -> None:
    """
    Processa um documento privado pertencente a um caso.

    Este pipeline é deliberadamente separado do corpus
    jurídico reutilizável.

    Ele:
    - extrai o conteúdo do arquivo;
    - preserva páginas/blocos e proveniência da extração;
    - aplica inspeção de segurança;
    - grava somente em CasoDocumento e CasoDocumentoPagina.

    Ele NÃO:
    - cria Documento;
    - cria DocumentoPagina;
    - cria DocumentoChunk;
    - gera embeddings;
    - adiciona conteúdo ao RAG jurídico.
    """

    db = SessionLocal()

    try:
        iniciar_tarefa(tarefa_id)
        documento = db.get(
            CasoDocumento,
            caso_documento_id,
        )

        if documento is None:
            logger.warning(
                "Documento de caso %s não encontrado para ingestão.",
                caso_documento_id,
            )
            falhar_tarefa(tarefa_id, "Documento não encontrado.")
            return

        documento.status = "PROCESSANDO"
        documento.erro_processamento = None
        documento.processado_em = None
        documento.status_seguranca = "PENDENTE"
        documento.alerta_seguranca = None

        db.commit()

        extracao = (
            extrair_documento(documento.caminho_arquivo, forcar_ocr=True)
            if forcar_ocr
            else extrair_documento(documento.caminho_arquivo)
        )

        paginas_com_texto = [
            (
                parte.numero,
                parte.conteudo,
            )
            for parte in extracao.partes
            if parte.conteudo
        ]

        if paginas_com_texto:
            inspecao = inspecionar_conteudo(paginas_com_texto)

            documento.status_seguranca = inspecao.status

            if inspecao.status == "REVISAO":
                documento.alerta_seguranca = (
                    "Foram identificadas instruções "
                    "potencialmente dirigidas à IA. "
                    "O conteúdo deve ser conferido "
                    "antes de ser utilizado "
                    "automaticamente na análise."
                )
            else:
                documento.alerta_seguranca = None

        else:
            documento.status_seguranca = "PENDENTE"
            documento.alerta_seguranca = (
                "Não há texto extraído suficiente "
                "para inspeção automática do conteúdo."
            )

        db.query(CasoDocumentoPagina).filter(
            CasoDocumentoPagina.caso_documento_id == documento.id
        ).delete(synchronize_session=False)

        extensao = Path(documento.nome_arquivo).suffix.lower()

        pagina_confiavel = extensao == ".pdf"

        for parte in extracao.partes:
            if pagina_confiavel:
                localizacao = f"Página {parte.numero}"
            else:
                localizacao = f"Bloco lógico {parte.numero}"

            db.add(
                CasoDocumentoPagina(
                    caso_documento_id=(documento.id),
                    pagina=parte.numero,
                    pagina_confiavel=(pagina_confiavel),
                    localizacao=localizacao,
                    conteudo=(parte.conteudo or ""),
                    metodo_extracao=(parte.metodo),
                    situacao_extracao=(parte.situacao),
                )
            )

        documento.total_paginas = len(extracao.partes)

        documento.situacao_extracao = extracao.situacao

        documento.diagnostico_extracao = extracao.resumo()

        if paginas_com_texto:
            documento.status = "PRONTO"
            documento.erro_processamento = None
        else:
            documento.status = "ERRO"

            if extracao.situacao == "NECESSITA_OCR":
                documento.erro_processamento = (
                    "O documento necessita de OCR " "antes de poder ser analisado."
                )
            else:
                documento.erro_processamento = (
                    "Não foi possível extrair texto " "utilizável do documento."
                )

        documento.processado_em = utc_now()

        db.commit()
        concluir_tarefa(tarefa_id)

    except Exception as erro:
        db.rollback()

        logger.error(
            ("Falha na ingestão do documento " "de caso %s (tipo=%s)."),
            caso_documento_id,
            type(erro).__name__,
        )

        documento = db.get(
            CasoDocumento,
            caso_documento_id,
        )

        if documento is not None:
            documento.status = "ERRO"

            documento.situacao_extracao = "ERRO_PROCESSAMENTO"

            documento.status_seguranca = "PENDENTE"

            documento.alerta_seguranca = None

            if isinstance(
                erro,
                FileNotFoundError,
            ):
                mensagem = (
                    "O arquivo do documento "
                    "não está disponível "
                    "para processamento."
                )

            else:
                mensagem = (
                    "Falha interna durante " "o processamento. " "Tente novamente."
                )

            documento.erro_processamento = mensagem[:500]

            documento.processado_em = utc_now()

            db.commit()
        falhar_tarefa(tarefa_id, "Falha interna durante o processamento.")

    finally:
        db.close()
        liberar_processamento(caso_documento_id)
