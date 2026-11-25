import uuid

from app.auth import get_current_user
from app.dependencies import get_db
from app.models import (
    Caso,
    ConsultaRevisao,
    Documento,
    IAExternaFila,
    IAExternaFonte,
    IAExternaStore,
    Usuario,
    utc_now,
)
from app.permissions import require_roles
from app.services.external_ai_service import (
    CLASSIFICACOES_EXTERNAS,
    disponibilidade_externa,
    liberar_documento_institucional,
    liberar_caso_sintetico,
    liberar_resposta_revisada,
    revogar_caso_externo,
    status_caso_externo,
    status_externo,
)
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/ia-externa", tags=["IA externa"])


class LiberacaoFonteUpdate(BaseModel):
    classificacao: str
    confirmou_politica_de_dados: bool = False
    confirmou_norma_publica_integral: bool = False
    confirmou_fonte_publica_integral: bool = False


class LiberacaoCasoUpdate(BaseModel):
    classificacao: str
    confirmou_conteudo_sintetico: bool = False
    confirmou_revisao_humana: bool = False


def _validar_liberacao(classificacao: str, confirmou: bool) -> str:
    valor = classificacao.strip().upper()
    if valor not in CLASSIFICACOES_EXTERNAS:
        raise HTTPException(status_code=422, detail="Classificação externa inválida.")
    if valor != "LOCAL_ONLY":
        if not confirmou:
            raise HTTPException(
                status_code=422,
                detail="Confirme que a fonte é pública ou sintética e pode ser enviada ao provedor.",
            )
        if not disponibilidade_externa():
            raise HTTPException(
                status_code=409,
                detail="Gateway indisponível. Configure-o no servidor e confirme o nível gratuito antes da liberação.",
            )
    return valor


@router.get("/status")
def obter_status(
    db: Session = Depends(get_db),
    _usuario: Usuario = Depends(require_roles("ADMIN")),
):
    return status_externo(db)


@router.patch("/documentos/{documento_id}")
def atualizar_liberacao_documento(
    documento_id: uuid.UUID,
    dados: LiberacaoFonteUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN")),
):
    documento = db.get(Documento, documento_id)
    if documento is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    classificacao = _validar_liberacao(
        dados.classificacao, dados.confirmou_politica_de_dados
    )
    confirmou_fonte_publica = (
        dados.confirmou_fonte_publica_integral or dados.confirmou_norma_publica_integral
    )
    if confirmou_fonte_publica and (
        classificacao != "PUBLICO" or documento.tipo not in {"NORMA", "LEGISLACAO", "ENTENDIMENTO", "PROCEDIMENTO", "MANUAL"}
    ):
        raise HTTPException(status_code=422, detail="Confirmação restrita a fontes institucionais públicas.")
    try:
        liberar_documento_institucional(
            db, documento, classificacao, usuario.id,
            confirmar_fonte_publica=confirmou_fonte_publica,
        )
        db.commit()
    except ValueError as erro:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A fonte não está elegível ou não passou pela inspeção local.",
        ) from erro
    return {
        "documento_id": str(documento.id),
        "classificacao": documento.liberacao_externa,
        "status": _status_documento(db, documento.id),
    }


@router.patch("/revisoes/{revisao_id}")
def atualizar_liberacao_revisao(
    revisao_id: uuid.UUID,
    dados: LiberacaoFonteUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN")),
):
    revisao = db.get(ConsultaRevisao, revisao_id)
    if revisao is None:
        raise HTTPException(status_code=404, detail="Revisão não encontrada.")
    classificacao = _validar_liberacao(
        dados.classificacao, dados.confirmou_politica_de_dados
    )
    try:
        liberar_resposta_revisada(db, revisao, classificacao, usuario.id)
        db.commit()
    except ValueError as erro:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A resposta final não está elegível ou não passou pela inspeção local.",
        ) from erro
    return {
        "revisao_id": str(revisao.id),
        "classificacao": classificacao,
        "status": _status_revisao(db, revisao.id),
    }


@router.patch("/casos/{caso_id}")
def atualizar_liberacao_caso_sintetico(
    caso_id: uuid.UUID,
    dados: LiberacaoCasoUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    caso = db.get(Caso, caso_id)
    if caso is None:
        raise HTTPException(status_code=404, detail="Caso não encontrado.")
    if (
        usuario.role != "ADMIN"
        and caso.criado_por != usuario.id
        and caso.responsavel_id != usuario.id
    ):
        raise HTTPException(status_code=404, detail="Caso não encontrado.")
    classificacao = dados.classificacao.strip().upper()
    if classificacao == "LOCAL_ONLY":
        revogar_caso_externo(db, caso)
        db.commit()
        return {
            "caso_id": str(caso.id),
            "classificacao": caso.classificacao_externa,
            "status": "LOCAL_ONLY",
        }
    if classificacao not in {"ANONIMIZADO", "SINTETICO"}:
        raise HTTPException(
            status_code=422,
            detail="Selecione o envio anonimizado ou mantenha os documentos somente locais.",
        )
    if classificacao == "SINTETICO" and (
        usuario.role != "ADMIN" or not dados.confirmou_conteudo_sintetico
    ):
        raise HTTPException(
            status_code=422,
            detail="A liberação de conteúdo sintético permanece restrita ao administrador.",
        )
    if classificacao == "ANONIMIZADO" and not dados.confirmou_revisao_humana:
        raise HTTPException(
            status_code=422,
            detail="Confirme que revisou e autorizou o envio das versões anonimizadas.",
        )
    try:
        total_paginas = liberar_caso_sintetico(
            db, caso, usuario.id, classificacao=classificacao
        )
        db.commit()
    except ValueError as erro:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "O caso não foi liberado. Confira se a integração está habilitada e se "
                "há ao menos um documento extraído e aprovado após a ocultação. Os demais "
                "permanecem somente locais."
            ),
        ) from erro
    return {
        "caso_id": str(caso.id),
        "classificacao": caso.classificacao_externa,
        "paginas_na_fila": total_paginas,
        "store_isolado_por_caso": True,
        "interacao_persistida_no_gemini": False,
        "documentos_guardados_em_store_remoto": True,
    }


@router.get("/casos/{caso_id}")
def obter_status_caso_sintetico(
    caso_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    caso = db.get(Caso, caso_id)
    if caso is None or (
        usuario.role != "ADMIN"
        and caso.criado_por != usuario.id
        and caso.responsavel_id != usuario.id
    ):
        raise HTTPException(status_code=404, detail="Caso não encontrado.")
    return status_caso_externo(db, caso)


@router.get("/fila")
def listar_fila(
    db: Session = Depends(get_db),
    _usuario: Usuario = Depends(require_roles("ADMIN")),
):
    jobs = (
        db.query(IAExternaFila)
        .order_by(IAExternaFila.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": str(job.id),
            "acao": job.acao,
            "status": job.status,
            "tentativas": job.tentativas,
            "erro_codigo": job.erro_codigo,
            "created_at": job.created_at,
            "concluido_em": job.concluido_em,
        }
        for job in jobs
    ]


@router.post("/fila/{job_id}/reprocessar", status_code=status.HTTP_202_ACCEPTED)
def reprocessar_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    _usuario: Usuario = Depends(require_roles("ADMIN")),
):
    job = db.get(IAExternaFila, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    if job.status != "ERRO":
        raise HTTPException(status_code=409, detail="Somente tarefas com erro podem ser reprocessadas.")
    job.status = "PENDENTE"
    job.tentativas = 0
    job.erro_codigo = None
    job.iniciado_em = None
    job.concluido_em = None
    job.proxima_tentativa_em = utc_now()
    db.commit()
    return {"id": str(job.id), "status": job.status}


def _status_documento(db: Session, documento_id: uuid.UUID) -> dict[str, int]:
    linhas = (
        db.query(IAExternaFonte.status)
        .filter(IAExternaFonte.documento_id == documento_id)
        .all()
    )
    resultado: dict[str, int] = {}
    for (estado,) in linhas:
        resultado[estado] = resultado.get(estado, 0) + 1
    return resultado


def _status_revisao(db: Session, revisao_id: uuid.UUID) -> dict[str, int]:
    linhas = (
        db.query(IAExternaFonte.status)
        .filter(IAExternaFonte.revisao_id == revisao_id)
        .all()
    )
    resultado: dict[str, int] = {}
    for (estado,) in linhas:
        resultado[estado] = resultado.get(estado, 0) + 1
    return resultado
