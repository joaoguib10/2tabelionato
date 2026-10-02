import pytest
from app.services import ollama_security


def test_ollama_local_e_permitido_por_padrao():
    assert ollama_security.ollama_local_permitido("http://localhost:11434")
    assert ollama_security.ollama_local_permitido("http://127.0.0.1:11434")
    assert ollama_security.ollama_local_permitido("http://[::1]:11434")


def test_ollama_remoto_e_bloqueado_no_modo_local():
    with pytest.raises(RuntimeError, match="loopback"):
        ollama_security.garantir_ollama_permitido("https://ollama.exemplo.invalid")
