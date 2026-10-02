import re
from dataclasses import dataclass

from app.prompts.base import FRONTEIRA_CONFIANCA_PROMPT as FRONTEIRA_CONFIANCA_PROMPT

STATUS_SEGURANCA = {"PENDENTE", "LIBERADO", "REVISAO"}


@dataclass(frozen=True)
class ResultadoInspecao:
    status: str
    alerta: str | None


PADROES_SUSPEITOS = (
    re.compile(
        r"\b(?:ignore|desconsidere|abandone)\b.{0,80}\b(?:instru[cç][oõ]es|regras|prompt)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:system prompt|prompt do sistema|developer message|mensagem de desenvolvedor)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:revele|exiba|mostre|forne[cç]a)\b.{0,80}\b(?:prompt|segredo|token|senha)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:execute|rode|chame|acesse)\b.{0,80}\b(?:comando|terminal|powershell|cmd|ferramenta)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"\bprompt[ -]?injection\b", re.IGNORECASE),
)


def inspecionar_conteudo(paginas: list[tuple[int, str]]) -> ResultadoInspecao:
    """Aplica a fronteira mínima de confiança antes do uso do documento pela IA."""
    texto = "\n".join(conteudo for _, conteudo in paginas)
    if any(padrao.search(texto) for padrao in PADROES_SUSPEITOS):
        return ResultadoInspecao(
            status="REVISAO",
            alerta=(
                "Foram identificadas instruções potencialmente dirigidas à IA. "
                "O documento exige revisão administrativa antes da publicação."
            ),
        )
    return ResultadoInspecao(status="LIBERADO", alerta=None)
