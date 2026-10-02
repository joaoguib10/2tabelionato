import bcrypt

MIN_PASSWORD_LENGTH = 5


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")

    password_hash = bcrypt.hashpw(
        password_bytes,
        bcrypt.gensalt(),
    )

    return password_hash.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if len(password.encode("utf-8")) > 72:
        return False
    password_bytes = password.encode("utf-8")
    hash_bytes = password_hash.encode("utf-8")

    return bcrypt.checkpw(
        password_bytes,
        hash_bytes,
    )


def validar_senha(password: str) -> str:
    if (
        len(password) < MIN_PASSWORD_LENGTH
        or len(password.encode("utf-8")) > 72
        or password.isspace()
    ):
        raise ValueError("Use uma senha de ao menos 5 caracteres e no máximo 72 bytes.")
    if not any(caractere.isalpha() for caractere in password) or not any(
        caractere.isdigit() for caractere in password
    ):
        raise ValueError("A senha deve conter pelo menos uma letra e um número.")
    return password
