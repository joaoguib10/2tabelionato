from urllib.parse import urlparse

from app.config import OLLAMA_BASE_URL, OLLAMA_LOCAL_ONLY

HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1"}


def ollama_local_permitido(url: str = OLLAMA_BASE_URL) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in HOSTS_LOCAIS


def garantir_ollama_permitido(url: str = OLLAMA_BASE_URL) -> None:
    if OLLAMA_LOCAL_ONLY and not ollama_local_permitido(url):
        raise RuntimeError("O processamento local exige OLLAMA_BASE_URL em loopback.")
