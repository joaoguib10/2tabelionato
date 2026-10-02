import json
import logging
import urllib.request
from types import MappingProxyType

from app.config import (
    OLLAMA_BASE_URL,
    OLLAMA_CONSULTA_CONTEXT_TOKENS,
    OLLAMA_CONSULTA_MAX_TOKENS,
    OLLAMA_CONSULTA_MODEL,
    OLLAMA_KEEP_ALIVE,
)
from app.prompts import (
    BASE_PROMPT_VERSION,
    CONSULTA_PROMPT_VERSION,
    CONSULTA_SYSTEM_PROMPT,
    build_consulta_prompt,
)
from app.services.ollama_security import garantir_ollama_permitido

OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
MODELO_GERACAO = OLLAMA_CONSULTA_MODEL
TIPO_TAREFA_CONSULTA = "CONSULTA"
CONSULTA_PROMPT_AUDIT_VERSION = f"{CONSULTA_PROMPT_VERSION}+base.{BASE_PROMPT_VERSION}"
OPCOES_GERACAO_CONSULTA = MappingProxyType(
    {
        "temperature": 0.1,
        "num_ctx": OLLAMA_CONSULTA_CONTEXT_TOKENS,
        "num_predict": OLLAMA_CONSULTA_MAX_TOKENS,
    }
)
logger = logging.getLogger(__name__)


def obter_metadados_consulta() -> dict[str, object]:
    """Retorna metadados auditáveis sem expor estado interno mutável."""
    return {
        "modelo": MODELO_GERACAO,
        "prompt_version": CONSULTA_PROMPT_AUDIT_VERSION,
        "tipo_tarefa": TIPO_TAREFA_CONSULTA,
        "parametros": dict(OPCOES_GERACAO_CONSULTA),
    }


def gerar_resposta(
    pergunta: str,
    contexto: str,
    historico: str = "",
) -> str:
    garantir_ollama_permitido()
    prompt = build_consulta_prompt(pergunta, contexto, historico)

    dados = {
        "model": MODELO_GERACAO,
        "messages": [
            {"role": "system", "content": CONSULTA_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "think": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": dict(OPCOES_GERACAO_CONSULTA),
    }

    requisicao = urllib.request.Request(
        OLLAMA_CHAT_URL,
        data=json.dumps(dados).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(
        requisicao,
        timeout=300,
    ) as resposta:
        resultado = json.loads(resposta.read().decode("utf-8"))

    mensagem = resultado.get("message")
    texto = mensagem.get("content") if isinstance(mensagem, dict) else None

    logger.info(
        "Geração Ollama concluída: modelo=%s entrada=%s tokens, saída=%s tokens, "
        "carga=%.2fs prefill=%.2fs geração=%.2fs total=%.2fs",
        MODELO_GERACAO,
        resultado.get("prompt_eval_count", "N/A"),
        resultado.get("eval_count", "N/A"),
        resultado.get("load_duration", 0) / 1_000_000_000,
        resultado.get("prompt_eval_duration", 0) / 1_000_000_000,
        resultado.get("eval_duration", 0) / 1_000_000_000,
        resultado.get("total_duration", 0) / 1_000_000_000,
    )

    if not texto:
        raise RuntimeError("O Ollama não retornou uma resposta.")

    return texto.strip()
