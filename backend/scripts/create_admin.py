from getpass import getpass

from app.database import SessionLocal
from app.models import Usuario
from app.security import hash_password, validar_senha


def create_admin():
    nome = input("Nome do usuário ADMIN: ").strip()
    username = input("Login do usuário ADMIN: ").strip().lower()

    if len(nome) < 2 or len(username) < 3:
        print("Informe um nome e um login válidos.")
        return

    senha = getpass("Digite a senha do ADMIN: ")
    confirmar_senha = getpass("Confirme a senha: ")

    try:
        validar_senha(senha)
    except ValueError as erro:
        print(str(erro))
        return

    if senha != confirmar_senha:
        print("As senhas não conferem.")
        return

    db = SessionLocal()

    try:
        usuario_existente = (
            db.query(Usuario).filter(Usuario.username == username).first()
        )

        if usuario_existente:
            print("Esse login já está cadastrado.")
            return

        usuario = Usuario(
            nome=nome,
            username=username,
            password_hash=hash_password(senha),
            role="ADMIN",
            ativo=True,
        )

        db.add(usuario)
        db.commit()

        print("Usuário ADMIN criado com sucesso!")

    except Exception:
        db.rollback()
        print("Não foi possível criar o usuário ADMIN. Verifique o banco local.")

    finally:
        db.close()


if __name__ == "__main__":
    create_admin()
