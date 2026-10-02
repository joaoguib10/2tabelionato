import pytest
from app.security import validar_senha


def test_senha_com_cinco_caracteres_e_letras_e_numeros_e_valida():
    assert validar_senha("abc12") == "abc12"


@pytest.mark.parametrize("senha", ["abcd", "12345", "abcdef"])
def test_senha_curta_ou_sem_letras_e_numeros_e_rejeitada(senha):
    with pytest.raises(ValueError):
        validar_senha(senha)
