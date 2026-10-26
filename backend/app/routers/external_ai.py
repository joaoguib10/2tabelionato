import uuid

from app.config import EXTERNAL_AI_CASES_ENABLED
from app.dependencies import get_db
from app.models import (
    ConsultaRevisao,
    Documento,
    IAExternaConfiguracao,
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
    liberar_resposta_revisada,
    status_externo,
)
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/ia-externa", tags=["IA externa"])


class ConfiguracaoExternaUpdate(BaseModel):
    consulta_habilitada: bool | None = None
    casos_sinteticos_habilitados: bool | None = None
    confirmou_politica_de_dados: bool = False


class LiberacaoFonteUpdate(BaseModel):
    classificacao: str
    confirmou_politica_de_dados: bool = False


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


@router.patch("/configuracao")
def atualizar_configuracao(
    dados: ConfiguracaoExternaUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMIN")),
):
    habilitando = any(
        valor is True
        for valor in (dados.consulta_habilitada, dados.casos_sinteticos_habilitados)
    )
    if habilitando and not dados.confirmou_politica_de_dados:
        raise HTTPException(
            status_code=422,
            detail="Confirme que somente conteúdo público ou sintético será enviado.",
        )
    if habilitando and not disponibilidade_externa():
        raise HTTPException(
            status_code=409,
            detail="Gateway indisponível. Verifique a configuração do servidor e do nível gratuito.",
        )
    if dados.casos_sinteticos_habilitados and not EXTERNAL_AI_CASES_ENABLED:
        raise HTTPException(
            status_code=409,
            detail="A análise externa de casos permanece bloqueada até a barreira de privacidade ser habilitada no servidor.",
        )

    configuracao = db.get(IAExternaConfiguracao, "global")
    if configuracao is None:
        configuracao = IAExternaConfiguracao(chave="global")
        db.add(configuracao)
    if dados.consulta_habilitada is not None:
        configuracao.consulta_habilitada = dados.consulta_habilitada
    if dados.casos_sinteticos_habilitados is not None:
        configuracao.casos_sinteticos_habilitados = dados.casos_sinteticos_habilitados
    configuracao.atualizado_por = usuario.id
    configuracao.updated_at = utc_now()
    db.commit()
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
    configuracao = db.get(IAExternaConfiguracao, "global")
    if classificacao != "LOCAL_ONLY" and not (
        configuracao and configuracao.consulta_habilitada
    ):
        raise HTTPException(
            status_code=409,
            detail="Habilite a Consulta externa nas Configurações antes de liberar uma fonte.",
        )
    try:
        liberar_documento_institucional(db, documento, classificacao, usuario.id)
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
    configuracao = db.get(IAExternaConfiguracao, "global")
    if classificacao != "LOCAL_ONLY" and not (
        configuracao and configuracao.consulta_habilitada
    ):
        raise HTTPException(
            status_code=409,
            detail="Habilite a Consulta externa nas Configurações antes de liberar uma fonte.",
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
