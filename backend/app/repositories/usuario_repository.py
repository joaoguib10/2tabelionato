from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Usuario


class UsuarioRepository:
    @staticmethod
    def listar(db: Session) -> list[Usuario]:
        return db.query(Usuario).order_by(Usuario.nome.asc()).all()

    @staticmethod
    def por_id(db: Session, usuario_id: UUID) -> Usuario | None:
        return db.query(Usuario).filter(Usuario.id == usuario_id).first()

    @staticmethod
    def por_username(db: Session, username: str) -> Usuario | None:
        return db.query(Usuario).filter(Usuario.username == username).first()

    @staticmethod
    def salvar(db: Session, usuario: Usuario) -> Usuario:
        db.commit()
        db.refresh(usuario)
        return usuario

    @staticmethod
    def adicionar(db: Session, usuario: Usuario) -> Usuario:
        db.add(usuario)
        return UsuarioRepository.salvar(db, usuario)

    @staticmethod
    def excluir(db: Session, usuario: Usuario) -> None:
        db.delete(usuario)
        db.commit()
