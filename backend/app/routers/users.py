from uuid import UUID

from app.dependencies import get_db
from app.models import Usuario
from app.permissions import require_roles
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas import (
    UsuarioCreate,
    UsuarioPasswordUpdate,
    UsuarioResponse,
    UsuarioStatusUpdate,
    UsuarioUpdate,
)
from app.security import hash_password
from app.services.two_factor import redefinir_acesso
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/api/usuarios",
    tags=["Usuários"],
)


def usuario_to_response(usuario: Usuario) -> UsuarioResponse:
    return UsuarioResponse(
        id=str(usuario.id),
        nome=usuario.nome,
        username=usuario.username,
        role=usuario.role,
        ativo=usuario.ativo,
    )


@router.get(
    "",
    response_model=list[UsuarioResponse],
)
def listar_usuarios(
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    usuarios = UsuarioRepository.listar(db)

    return [usuario_to_response(usuario) for usuario in usuarios]


@router.post(
    "",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
)
def criar_usuario(
    dados: UsuarioCreate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):

    username = dados.username.strip().lower()

    username_existente = UsuarioRepository.por_username(db, username)

    if username_existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este nome de usuário já está em uso.",
        )

    if dados.role not in {"ADMIN", "USUARIO"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Perfil de usuário inválido.",
        )

    usuario = Usuario(
        nome=dados.nome.strip(),
        username=username,
        password_hash=hash_password(dados.password),
        role=dados.role,
        ativo=True,
    )

    UsuarioRepository.adicionar(db, usuario)

    return usuario_to_response(usuario)


@router.put(
    "/{usuario_id}",
    response_model=UsuarioResponse,
)
def atualizar_usuario(
    usuario_id: UUID,
    dados: UsuarioUpdate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    usuario = UsuarioRepository.por_id(db, usuario_id)

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado.",
        )

    if usuario.id == usuario_atual.id and dados.role is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode alterar o próprio perfil.",
        )

    if dados.nome is not None:
        usuario.nome = dados.nome.strip()

    if dados.role is not None:
        if dados.role not in {"ADMIN", "USUARIO"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Perfil de usuário inválido.",
            )

        usuario.role = dados.role
        usuario.sessao_versao += 1

    UsuarioRepository.salvar(db, usuario)

    return usuario_to_response(usuario)


@router.patch(
    "/{usuario_id}/status",
    response_model=UsuarioResponse,
)
def alterar_status_usuario(
    usuario_id: UUID,
    dados: UsuarioStatusUpdate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    usuario = UsuarioRepository.por_id(db, usuario_id)

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado.",
        )

    if usuario.id == usuario_atual.id and not dados.ativo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode desativar o próprio usuário.",
        )

    usuario.ativo = dados.ativo
    usuario.sessao_versao += 1

    UsuarioRepository.salvar(db, usuario)

    return usuario_to_response(usuario)


@router.patch(
    "/{usuario_id}/senha",
    status_code=status.HTTP_204_NO_CONTENT,
)
def redefinir_senha(
    usuario_id: UUID,
    dados: UsuarioPasswordUpdate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    usuario = UsuarioRepository.por_id(db, usuario_id)

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado.",
        )

    if usuario.role == "ADMIN":
        raise HTTPException(
            403, "Recupere contas ADMIN pelo procedimento local no servidor."
        )
    redefinir_acesso(db, usuario, hash_password(dados.password), usuario_atual)

    UsuarioRepository.salvar(db, usuario)

    return None


@router.delete(
    "/{usuario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def excluir_usuario(
    usuario_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    usuario = UsuarioRepository.por_id(db, usuario_id)

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado.",
        )

    if usuario.id == usuario_atual.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode excluir o próprio usuário.",
        )

    UsuarioRepository.excluir(db, usuario)

    return None
