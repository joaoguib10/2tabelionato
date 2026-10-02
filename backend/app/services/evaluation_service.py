import re
import unicodedata


def _normalizar(texto: str) -> str:
    decompleto = unicodedata.normalize("NFD", texto.casefold())
    return "".join(
        caractere for caractere in decompleto if unicodedata.category(caractere) != "Mn"
    )


def avaliar_resposta_esperada(
    resposta: str,
    termos_esperados: list[str],
    termos_proibidos: list[str] | None = None,
    fontes_esperadas: list[str] | None = None,
) -> dict:
    texto = _normalizar(resposta)
    ausentes = [termo for termo in termos_esperados if _normalizar(termo) not in texto]
    proibidos = [
        termo for termo in (termos_proibidos or []) if _normalizar(termo) in texto
    ]
    fontes_citadas = set(re.findall(r"\[(FONTE-[0-9a-fA-F-]{36})\]", resposta))
    fontes_ausentes = [
        fonte for fonte in (fontes_esperadas or []) if fonte not in fontes_citadas
    ]

    return {
        "aprovada": not ausentes and not proibidos and not fontes_ausentes,
        "termos_ausentes": ausentes,
        "termos_proibidos_encontrados": proibidos,
        "fontes_ausentes": fontes_ausentes,
    }


def avaliar_resultado_pipeline(
    caso: dict,
    resposta: str,
    situacao_resposta: str,
    fontes_utilizadas: list[dict],
) -> dict:
    avaliacao = avaliar_resposta_esperada(
        resposta,
        caso.get("termos_esperados", []),
        caso.get("termos_proibidos", []),
    )
    recusa_esperada = bool(caso.get("expectativa_recusa"))
    recusa_correta = (
        situacao_resposta == "BASE_INSUFICIENTE"
        if recusa_esperada
        else situacao_resposta != "BASE_INSUFICIENTE"
    )
    fonte_esperada = caso.get("fonte_esperada")
    fonte_correta = True
    if fonte_esperada:
        fonte_correta = any(
            fonte.get("documento") == fonte_esperada.get("titulo")
            and (
                not fonte_esperada.get("artigo")
                or fonte.get("artigo") == fonte_esperada.get("artigo")
            )
            for fonte in fontes_utilizadas
        )
    avaliacao.update(
        {
            "recusa_correta": recusa_correta,
            "fonte_correta": fonte_correta,
            "aprovada": avaliacao["aprovada"] and recusa_correta and fonte_correta,
        }
    )
    return avaliacao
