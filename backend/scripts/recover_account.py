"""Recuperação presencial: nunca recebe senha por argumentos ou imprime segredos."""

from getpass import getpass

from app.database import SessionLocal
from app.models import Usuario
from app.security import hash_password, validar_senha
from app.services.two_factor import redefinir_acesso


def main():
    print("Recuperação local de acesso. Execute somente no servidor autorizado.")
    username = input("Login a recuperar: ").strip().lower()
    password = getpass(
        "Nova senha temporária (mínimo 5 caracteres, letras e números): "
    )
    try:
        validar_senha(password)
    except ValueError as exc:
        print(str(exc))
        return 1
    if password != getpass("Repita a senha: "):
        print("As senhas não coincidem. Nada foi alterado.")
        return 1
    if (
        input(
            "Digite RECUPERAR para invalidar sessões, autenticador e códigos anteriores: "
        )
        != "RECUPERAR"
    ):
        print("Cancelado. Nada foi alterado.")
        return 1
    try:
        with SessionLocal.begin() as db:
            usuario = (
                db.query(Usuario)
                .filter(Usuario.username == username)
                .with_for_update()
                .first()
            )
            if not usuario or not usuario.ativo:
                print("Conta inexistente ou inativa. Nada foi alterado.")
                return 1
            redefinir_acesso(db, usuario, hash_password(password))
    except Exception:
        print(
            "Não foi possível recuperar a conta. Verifique o banco local e as migrações."
        )
        return 1
    print(
        "Acesso redefinido e operação auditada. Entre com a senha temporária e cadastre nova senha e autenticador."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
