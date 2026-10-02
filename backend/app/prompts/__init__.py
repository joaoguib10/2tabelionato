"""Builders e versões dos prompts enviados aos modelos locais."""

from app.prompts.analise_documental import (
    ANALISE_DOCUMENTAL_PROMPT_VERSION,
    ANALISE_DOCUMENTAL_TEXT_LIMIT,
    build_analise_imagem_prompt,
    build_estruturacao_documental_prompt,
)
from app.prompts.analise_juridica import (
    ANALISE_JURIDICA_PROMPT_VERSION,
    build_analise_juridica_prompt,
)
from app.prompts.base import (
    BASE_PROMPT_VERSION,
    REGRAS_GLOBAIS_PROMPT,
    build_base_prompt,
)
from app.prompts.compra_venda import (
    COMPRA_VENDA_PROMPT_VERSION,
    build_compra_venda_prompt,
)
from app.prompts.consulta import (
    CONSULTA_PROMPT_VERSION,
    CONSULTA_SYSTEM_PROMPT,
    build_consulta_prompt,
)
from app.prompts.estado_factual import (
    ESTADO_FACTUAL_PROMPT_VERSION,
    build_estado_factual_prompt,
)
from app.prompts.minuta import MINUTA_PROMPT_VERSION, build_minuta_prompt

PROMPT_VERSIONS = {
    "base": BASE_PROMPT_VERSION,
    "consulta": CONSULTA_PROMPT_VERSION,
    "estado_factual": ESTADO_FACTUAL_PROMPT_VERSION,
    "compra_venda": COMPRA_VENDA_PROMPT_VERSION,
    "analise_documental": ANALISE_DOCUMENTAL_PROMPT_VERSION,
    "analise_juridica": ANALISE_JURIDICA_PROMPT_VERSION,
    "minuta": MINUTA_PROMPT_VERSION,
}

__all__ = [
    "ANALISE_DOCUMENTAL_PROMPT_VERSION",
    "ANALISE_DOCUMENTAL_TEXT_LIMIT",
    "ANALISE_JURIDICA_PROMPT_VERSION",
    "BASE_PROMPT_VERSION",
    "CONSULTA_PROMPT_VERSION",
    "CONSULTA_SYSTEM_PROMPT",
    "ESTADO_FACTUAL_PROMPT_VERSION",
    "MINUTA_PROMPT_VERSION",
    "PROMPT_VERSIONS",
    "REGRAS_GLOBAIS_PROMPT",
    "build_analise_imagem_prompt",
    "build_analise_juridica_prompt",
    "build_base_prompt",
    "build_consulta_prompt",
    "build_estado_factual_prompt",
    "COMPRA_VENDA_PROMPT_VERSION",
    "build_compra_venda_prompt",
    "build_estruturacao_documental_prompt",
    "build_minuta_prompt",
]
