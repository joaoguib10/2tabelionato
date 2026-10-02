import hashlib
import math
import uuid
from pathlib import Path

from app.dependencies import get_db
from app.models import (
    ConsultaFonte,
    ConsultaHistorico,
    ConsultaRevisao,
    Documento,
    Usuario,
    utc_now,
)
from app.permissions import require_roles
from app.schemas import (
    ConsultaFonteHistoricoResponse,
    EntendimentoInternoCreate,
    EntendimentoInternoResponse,
    RevisaoListResponse,
    RevisaoResponse,
    RevisaoRespostaRequest,
    RevisaoStatusUpdate,
)
from app.services.ingestion_service import processar_documento
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/revisoes", tags=["Revisões"])
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "documentos"
STATUS_REVISAO = {"PENDENTE", "EM_ANALISE", "RESPONDIDA", "ENCERRADA"}


def _texto_opcional(valor: str | None) -> str | None:
    return valor.strip() if valor and valor.strip() else None


def _usuarios_por_id(
    db: Session,
    ids: set[uuid.UUID],
) -> dict[uuid.UUID, Usuario]:
    if not ids:
        return {}
    return {
        usuario.id: usuario
        for usuario in db.query(Usuario).filter(Usuario.id.in_(ids)).all()
    }


def _fontes_por_consulta(
    db: Session,
    ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[ConsultaFonte]]:
    fontes = {consulta_id: [] for consulta_id in ids}
    if not ids:
        return fontes
    for fonte in (
        db.query(ConsultaFonte)
        .filter(ConsultaFonte.consulta_id.in_(ids))
        .order_by(ConsultaFonte.created_at.asc())
        .all()
    ):
        fontes.setdefault(fonte.consulta_id, []).append(fonte)
    return fontes


def _fonte_response(fonte: ConsultaFonte) -> ConsultaFonteHistoricoResponse:
    return ConsultaFonteHistoricoResponse(
        fonte_id=fonte.fonte_id,
        documento_id=str(fonte.documento_id) if fonte.documento_id else None,
        titulo_documento=fonte.titulo_documento,
        versao_documento=fonte.versao_documento,
        pagina=fonte.pagina,
        localizacao=fonte.localizacao,
        artigo=fonte.artigo,
        trecho=fonte.trecho,
        pontuacao=fonte.pontuacao,
        citada=fonte.citada,
        recuperada=fonte.recuperada,
    )


def _revisao_response(
    revisao: ConsultaRevisao,
    consulta: ConsultaHistorico,
    autor: Usuario,
    usuarios: dict[uuid.UUID, Usuario],
    fontes: list[ConsultaFonte],
) -> RevisaoResponse:
    responsavel = usuarios.get(revisao.responsavel_id)
    respondente = usuarios.get(revisao.respondido_por)
    return RevisaoResponse(
        id=str(revisao.id),
        consulta_id=str(consulta.id),
        status=revisao.status,
        responsavel_id=str(revisao.responsavel_id) if revisao.responsavel_id else None,
        responsavel_nome=responsavel.nome if responsavel else None,
        resposta_humana=revisao.resposta_humana,
        respondido_por=str(revisao.respondido_por) if revisao.respondido_por else None,
        respondido_por_nome=respondente.nome if respondente else None,
        respondido_por_role=respondente.role if respondente else None,
        respondida_em=revisao.respondida_em,
        entendimento_documento_id=(
            str(revisao.entendimento_documento_id)
            if revisao.entendimento_documento_id
            else None
        ),
        encerrada_em=revisao.encerrada_em,
        created_at=revisao.created_at,
        updated_at=revisao.updated_at,
        usuario_id=str(autor.id),
        usuario_nome=autor.nome,
        usuario_username=autor.username,
        pergunta=consulta.pergunta,
        resposta_ia=consulta.resposta,
        situacao_resposta=consulta.situacao_resposta,
        produtiva=consulta.produtiva,
        feedback_motivo=consulta.feedback_motivo,
        feedback_comentario=consulta.feedback_comentario,
        fontes=[_fonte_response(fonte) for fonte in fontes],
    )


def _obter_linha(
    db: Session,
    revisao_id: uuid.UUID,
) -> tuple[ConsultaRevisao, ConsultaHistorico, Usuario]:
    linha = (
        db.query(ConsultaRevisao, ConsultaHistorico, Usuario)
        .join(
            ConsultaHistorico,
            ConsultaHistorico.id == ConsultaRevisao.consulta_id,
        )
        .join(Usuario, Usuario.id == ConsultaHistorico.usuario_id)
        .filter(ConsultaRevisao.id == revisao_id)
        .first()
    )
    if linha is None:
        raise HTTPException(status_code=404, detail="Revisão não encontrada.")
    return linha


def _resposta_atual(db: Session, revisao_id: uuid.UUID) -> RevisaoResponse:
    revisao, consulta, autor = _obter_linha(db, revisao_id)
    ids_usuarios = {
        identificador
        for identificador in (revisao.responsavel_id, revisao.respondido_por)
        if identificador is not None
    }
    fontes = _fontes_por_consulta(db, [consulta.id]).get(consulta.id, [])
    return _revisao_response(
        revisao,
        consulta,
        autor,
        _usuarios_por_id(db, ids_usuarios),
        fontes,
    )


@router.get("", response_model=RevisaoListResponse)
def listar_revisoes(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    situacao: str | None = None,
    usuario_id: uuid.UUID | None = None,
    responsavel_id: uuid.UUID | None = None,
    texto: str | None = None,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    consulta_db = (
        db.query(ConsultaRevisao, ConsultaHistorico, Usuario)
        .join(
            ConsultaHistorico,
            ConsultaHistorico.id == ConsultaRevisao.consulta_id,
        )
        .join(Usuario, Usuario.id == ConsultaHistorico.usuario_id)
    )
    if situacao:
        situacao_normalizada = situacao.strip().upper()
        if situacao_normalizada not in STATUS_REVISAO:
            raise HTTPException(status_code=422, detail="Situação de revisão inválida.")
        consulta_db = consulta_db.filter(ConsultaRevisao.status == situacao_normalizada)
    if usuario_id:
        consulta_db = consulta_db.filter(ConsultaHistorico.usuario_id == usuario_id)
    if responsavel_id:
        consulta_db = consulta_db.filter(
            ConsultaRevisao.responsavel_id == responsavel_id
        )
    if texto and texto.strip():
        termo = f"%{texto.strip()}%"
        consulta_db = consulta_db.filter(
            or_(
                ConsultaHistorico.pergunta.ilike(termo),
                ConsultaHistorico.feedback_comentario.ilike(termo),
            )
        )

    total = consulta_db.count()
    linhas = (
        consulta_db.order_by(ConsultaRevisao.created_at.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )
    ids_usuarios = {
        identificador
        for revisao, _, _ in linhas
        for identificador in (revisao.responsavel_id, revisao.respondido_por)
        if identificador is not None
    }
    usuarios = _usuarios_por_id(db, ids_usuarios)
    fontes = _fontes_por_consulta(db, [consulta.id for _, consulta, _ in linhas])
    return RevisaoListResponse(
        items=[
            _revisao_response(
                revisao,
                consulta,
                autor,
                usuarios,
                fontes.get(consulta.id, []),
            )
            for revisao, consulta, autor in linhas
        ],
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        total_paginas=math.ceil(total / por_pagina) if total else 0,
    )


@router.patch("/{revisao_id}/status", response_model=RevisaoResponse)
def alterar_status_revisao(
    revisao_id: uuid.UUID,
    dados: RevisaoStatusUpdate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    revisao, _, _ = _obter_linha(db, revisao_id)
    if dados.responsavel_id:
        responsavel = db.get(Usuario, dados.responsavel_id)
        if responsavel is None or not responsavel.ativo or responsavel.role != "ADMIN":
            raise HTTPException(status_code=422, detail="Responsável inválido.")
        revisao.responsavel_id = responsavel.id
    elif dados.status == "EM_ANALISE" and revisao.responsavel_id is None:
        revisao.responsavel_id = usuario_atual.id

    if dados.status == "RESPONDIDA" and not revisao.resposta_humana:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registre a resposta humana antes de concluir a revisão.",
        )
    if dados.status == "ENCERRADA" and not revisao.resposta_humana:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registre a resposta humana antes de encerrar a revisão.",
        )
    if dados.status == "PENDENTE":
        revisao.responsavel_id = None
    revisao.status = dados.status
    revisao.encerrada_em = utc_now() if dados.status == "ENCERRADA" else None
    db.commit()
    return _resposta_atual(db, revisao.id)


@router.post("/{revisao_id}/resposta", response_model=RevisaoResponse)
def registrar_resposta_humana(
    revisao_id: uuid.UUID,
    dados: RevisaoRespostaRequest,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    revisao, _, _ = _obter_linha(db, revisao_id)
    if revisao.resposta_humana is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A resposta humana já foi registrada e permanece preservada para "
                "auditoria."
            ),
        )
    revisao.resposta_humana = dados.resposta_humana.strip()
    revisao.responsavel_id = usuario_atual.id
    revisao.respondido_por = usuario_atual.id
    revisao.respondida_em = utc_now()
    revisao.encerrada_em = None
    revisao.status = "RESPONDIDA"
    db.commit()
    return _resposta_atual(db, revisao.id)


@router.post(
    "/{revisao_id}/entendimento",
    response_model=EntendimentoInternoResponse,
    status_code=status.HTTP_201_CREATED,
)
def transformar_em_entendimento(
    revisao_id: uuid.UUID,
    dados: EntendimentoInternoCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    revisao, _, _ = _obter_linha(db, revisao_id)
    if revisao.resposta_humana is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A revisão precisa de uma resposta humana antes da generalização.",
        )
    if revisao.entendimento_documento_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta revisão já foi transformada em entendimento.",
        )

    texto = dados.texto_generalizado.strip()
    resumo_hash = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    if db.query(Documento).filter(Documento.hash_arquivo == resumo_hash).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este entendimento já está cadastrado na base documental.",
        )

    documento_id = uuid.uuid4()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    caminho = UPLOAD_DIR / f"entendimento-interno-{documento_id}.txt"
    try:
        caminho.write_text(texto, encoding="utf-8")
        documento = Documento(
            id=documento_id,
            titulo=dados.titulo.strip(),
            descricao=None,
            tipo="ENTENDIMENTO",
            tipo_ato=None,
            situacao="RASCUNHO",
            orgao_origem=_texto_opcional(dados.origem),
            versao=_texto_opcional(dados.versao),
            jurisdicao=_texto_opcional(dados.abrangencia),
            observacoes=_texto_opcional(dados.observacao),
            nome_arquivo=caminho.name,
            caminho_arquivo=str(caminho),
            hash_arquivo=resumo_hash,
            status_seguranca="PENDENTE",
            ativo=True,
            status="PROCESSANDO",
            criado_por=usuario_atual.id,
        )
        db.add(documento)
        db.flush()
        revisao.entendimento_documento_id = documento.id
        db.commit()
        db.refresh(documento)
    except Exception:
        db.rollback()
        if caminho.exists():
            caminho.unlink()
        raise

    background_tasks.add_task(processar_documento, documento.id)
    return EntendimentoInternoResponse(
        id=str(documento.id),
        titulo=documento.titulo,
        situacao=documento.situacao,
        status=documento.status,
        tipo=documento.tipo,
    )
