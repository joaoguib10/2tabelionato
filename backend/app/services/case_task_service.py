"""Atualização pequena e transacional da fila persistente de casos."""

from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models import CasoTarefa, utc_now


def iniciar_tarefa(tarefa_id: UUID | None) -> None:
    if tarefa_id is None:
        return
    db = SessionLocal()
    try:
        tarefa = db.get(CasoTarefa, tarefa_id)
        if tarefa is None:
            return
        tarefa.status = "PROCESSANDO"
        tarefa.tentativa += 1
        tarefa.iniciado_em = utc_now()
        tarefa.erro = None
        db.commit()
    except SQLAlchemyError:
        # Compatibilidade com fixtures legadas que ainda não criam as tabelas
        # auxiliares; a execução principal não deve ser interrompida.
        db.rollback()
    finally:
        db.close()


def concluir_tarefa(tarefa_id: UUID | None) -> None:
    if tarefa_id is None:
        return
    db = SessionLocal()
    try:
        tarefa = db.get(CasoTarefa, tarefa_id)
        if tarefa is None:
            return
        tarefa.status = "CONCLUIDA"
        tarefa.concluido_em = utc_now()
        db.commit()
    except SQLAlchemyError:
        db.rollback()
    finally:
        db.close()


def falhar_tarefa(tarefa_id: UUID | None, mensagem: str) -> None:
    if tarefa_id is None:
        return
    db = SessionLocal()
    try:
        tarefa = db.get(CasoTarefa, tarefa_id)
        if tarefa is None:
            return
        tarefa.status = "ERRO"
        tarefa.erro = mensagem[:500]
        tarefa.concluido_em = utc_now()
        db.commit()
    except SQLAlchemyError:
        db.rollback()
    finally:
        db.close()
