"""Trabalhos temporários da Ata Notarial; não integram histórico nem RAG."""

import hashlib
import shutil
from pathlib import Path
from uuid import UUID, uuid4

from app.auth import get_current_user
from app.config import ATA_MAX_UPLOAD_BYTES
from app.dependencies import get_db
from app.models import AtaTrabalho, Usuario
from app.schemas import (
    AtaProcessoCreate,
    AtaTrabalhoListResponse,
    AtaTrabalhoResponse,
)
from app.services.notarial_act_service import processar_ata
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/atas", tags=["Ata Notarial"])
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "atas"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _resposta(trabalho: AtaTrabalho) -> AtaTrabalhoResponse:
    return AtaTrabalhoResponse(
        id=str(trabalho.id),
        titulo=trabalho.titulo,
        status=trabalho.status,
        nome_arquivo=trabalho.nome_arquivo,
        resultado=trabalho.resultado,
        diagnostico=trabalho.diagnostico,
        erro_processamento=trabalho.erro_processamento,
        created_at=trabalho.created_at,
        concluido_em=trabalho.concluido_em,
    )


def _obter(db: Session, trabalho_id: UUID, usuario: Usuario) -> AtaTrabalho:
    trabalho = db.get(AtaTrabalho, trabalho_id)
    if trabalho is None or trabalho.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Trabalho de Ata não encontrado.")
    return trabalho


def _pasta_segura(trabalho: AtaTrabalho) -> Path | None:
    if not trabalho.caminho_temporario:
        return None
    caminho = Path(trabalho.caminho_temporario).resolve()
    raiz = UPLOAD_DIR.resolve()
    try:
        relativo = caminho.relative_to(raiz)
    except ValueError:
        return None
    return raiz / relativo.parts[0] if relativo.parts else None


@router.get("", response_model=AtaTrabalhoListResponse)
def listar_trabalhos(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    trabalhos = (
        db.query(AtaTrabalho)
        .filter(AtaTrabalho.usuario_id == usuario.id)
        .order_by(AtaTrabalho.created_at.desc())
        .limit(20)
        .all()
    )
    return AtaTrabalhoListResponse(
        items=[_resposta(item) for item in trabalhos], total=len(trabalhos)
    )


@router.get("/{trabalho_id}", response_model=AtaTrabalhoResponse)
def obter_trabalho(
    trabalho_id: UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    return _resposta(_obter(db, trabalho_id, usuario))


@router.post(
    "/processos",
    response_model=AtaTrabalhoResponse,
    status_code=status.HTTP_201_CREATED,
)
def criar_processo(
    dados: AtaProcessoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    trabalho = AtaTrabalho(
        usuario_id=usuario.id,
        titulo=dados.titulo,
        status="ABERTO",
    )
    db.add(trabalho)
    db.commit()
    db.refresh(trabalho)
    return _resposta(trabalho)


async def _anexar_exportacao(
    trabalho: AtaTrabalho,
    arquivo: UploadFile,
    background_tasks: BackgroundTasks,
    db: Session,
) -> AtaTrabalhoResponse:
    nome = Path(arquivo.filename or "").name
    extensao = Path(nome).suffix.lower()
    if not nome or extensao not in {".zip", ".rar"}:
        raise HTTPException(status_code=400, detail="Envie uma exportação ZIP ou RAR.")

    pasta = UPLOAD_DIR / str(trabalho.id)
    try:
        pasta.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise HTTPException(
            status_code=409,
            detail="Já existe um arquivo temporário vinculado a este processo.",
        ) from None

    destino = pasta / f"exportacao{extensao}"
    tamanho = 0
    resumo = hashlib.sha256()
    try:
        with destino.open("wb") as saida:
            while bloco := await arquivo.read(1024 * 1024):
                tamanho += len(bloco)
                if tamanho > ATA_MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="A exportação excede o limite configurado.",
                    )
                resumo.update(bloco)
                saida.write(bloco)
        if tamanho == 0:
            raise HTTPException(status_code=400, detail="A exportação está vazia.")
        with destino.open("rb") as entrada:
            assinatura = entrada.read(8)
        assinatura_valida = (
            assinatura.startswith(b"PK")
            if extensao == ".zip"
            else assinatura.startswith(b"Rar!\x1a\x07")
        )
        if not assinatura_valida:
            raise HTTPException(
                status_code=400,
                detail=f"O conteúdo não corresponde a um arquivo {extensao[1:].upper()}.",
            )

        trabalho.nome_arquivo = nome
        trabalho.hash_arquivo = resumo.hexdigest()
        trabalho.caminho_temporario = str(destino)
        trabalho.status = "PROCESSANDO"
        trabalho.resultado = None
        trabalho.diagnostico = None
        trabalho.erro_processamento = None
        trabalho.concluido_em = None
        db.commit()
        db.refresh(trabalho)
        background_tasks.add_task(processar_ata, trabalho.id)
        return _resposta(trabalho)
    except HTTPException:
        db.rollback()
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    except Exception as erro:
        db.rollback()
        shutil.rmtree(pasta, ignore_errors=True)
        raise HTTPException(
            status_code=500, detail="Não foi possível receber a exportação."
        ) from erro
    finally:
        await arquivo.close()


@router.post(
    "/{trabalho_id}/arquivo",
    response_model=AtaTrabalhoResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def anexar_exportacao_ao_processo(
    trabalho_id: UUID,
    background_tasks: BackgroundTasks,
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    trabalho = _obter(db, trabalho_id, usuario)
    if trabalho.status != "ABERTO" or trabalho.caminho_temporario:
        raise HTTPException(
            status_code=409,
            detail="Este processo já recebeu uma exportação ou está em processamento.",
        )
    return await _anexar_exportacao(trabalho, arquivo, background_tasks, db)


@router.post(
    "", response_model=AtaTrabalhoResponse, status_code=status.HTTP_202_ACCEPTED
)
async def enviar_exportacao(
    background_tasks: BackgroundTasks,
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    nome = Path(arquivo.filename or "").name
    extensao = Path(nome).suffix.lower()
    if not nome or extensao not in {".zip", ".rar"}:
        raise HTTPException(status_code=400, detail="Envie uma exportação ZIP ou RAR.")
    identificador = uuid4()
    pasta = UPLOAD_DIR / str(identificador)
    pasta.mkdir(parents=True, exist_ok=False)
    destino = pasta / f"exportacao{extensao}"
    tamanho = 0
    resumo = hashlib.sha256()
    try:
        with destino.open("wb") as saida:
            while bloco := await arquivo.read(1024 * 1024):
                tamanho += len(bloco)
                if tamanho > ATA_MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="A exportação excede o limite configurado.",
                    )
                resumo.update(bloco)
                saida.write(bloco)
        if tamanho == 0:
            raise HTTPException(status_code=400, detail="A exportação está vazia.")
        with destino.open("rb") as entrada:
            assinatura = entrada.read(8)
        if extensao == ".zip" and not assinatura.startswith(b"PK"):
            raise HTTPException(
                status_code=400, detail="O conteúdo não corresponde a um arquivo ZIP."
            )
        if extensao == ".rar" and not assinatura.startswith(b"Rar!\x1a\x07"):
            raise HTTPException(
                status_code=400, detail="O conteúdo não corresponde a um arquivo RAR."
            )
        trabalho = AtaTrabalho(
            id=identificador,
            usuario_id=usuario.id,
            titulo=Path(nome).stem[:200] or "Ata Notarial",
            status="PROCESSANDO",
            nome_arquivo=nome,
            hash_arquivo=resumo.hexdigest(),
            caminho_temporario=str(destino),
        )
        db.add(trabalho)
        db.commit()
        db.refresh(trabalho)
        background_tasks.add_task(processar_ata, trabalho.id)
        return _resposta(trabalho)
    except HTTPException:
        db.rollback()
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    except Exception as erro:
        db.rollback()
        shutil.rmtree(pasta, ignore_errors=True)
        raise HTTPException(
            status_code=500, detail="Não foi possível receber a exportação."
        ) from erro
    finally:
        await arquivo.close()


@router.post(
    "/{trabalho_id}/reprocessar",
    response_model=AtaTrabalhoResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def reprocessar_exportacao(
    trabalho_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    trabalho = _obter(db, trabalho_id, usuario)
    if trabalho.status == "PROCESSANDO":
        raise HTTPException(
            status_code=409, detail="O trabalho ainda está em processamento."
        )
    caminho = Path(trabalho.caminho_temporario or "")
    if not caminho.is_file():
        raise HTTPException(
            status_code=404, detail="A exportação temporária não está mais disponível."
        )
    trabalho.status = "PROCESSANDO"
    trabalho.resultado = None
    trabalho.diagnostico = None
    trabalho.erro_processamento = None
    trabalho.concluido_em = None
    db.commit()
    db.refresh(trabalho)
    background_tasks.add_task(processar_ata, trabalho.id)
    return _resposta(trabalho)


@router.delete("/{trabalho_id}", status_code=status.HTTP_204_NO_CONTENT)
def concluir_e_descartar(
    trabalho_id: UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    trabalho = _obter(db, trabalho_id, usuario)
    if trabalho.status == "PROCESSANDO":
        raise HTTPException(
            status_code=409, detail="Aguarde o processamento antes de concluir."
        )
    if not trabalho.caminho_temporario:
        db.delete(trabalho)
        db.commit()
        return None
    pasta = _pasta_segura(trabalho)
    if pasta is None:
        raise HTTPException(
            status_code=409,
            detail="Área temporária inválida; descarte manual necessário.",
        )
    try:
        if pasta.exists():
            shutil.rmtree(pasta)
    except OSError as erro:
        raise HTTPException(
            status_code=500,
            detail="Não foi possível apagar todos os arquivos temporários. Tente novamente.",
        ) from erro
    db.delete(trabalho)
    db.commit()
    return None
