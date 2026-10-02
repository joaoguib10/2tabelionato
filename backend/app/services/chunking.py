import re

TAMANHO_CHUNK = 1500
SOBREPOSICAO = 200


PADRAO_ARTIGO = re.compile(r"(?im)^\s*(Art\.\s*\d+(?:-[A-Z])?(?:\.\d+)?)\b")


def normalizar_texto(texto: str) -> str:
    texto = texto.replace("\r\n", "\n")
    texto = texto.replace("\r", "\n")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def dividir_texto(
    texto: str,
    tamanho: int = TAMANHO_CHUNK,
    sobreposicao: int = SOBREPOSICAO,
) -> list[str]:
    texto = normalizar_texto(texto)

    if not texto:
        return []

    if sobreposicao >= tamanho:
        raise ValueError("A sobreposição deve ser menor que o tamanho do chunk.")

    blocos = _dividir_por_artigos(texto)

    if not blocos:
        return _dividir_texto_generico(
            texto,
            tamanho,
            sobreposicao,
        )

    chunks = []

    for bloco in blocos:
        if len(bloco) <= tamanho:
            chunks.append(bloco)
            continue

        chunks.extend(
            _dividir_texto_generico(
                bloco,
                tamanho,
                sobreposicao,
            )
        )

    return chunks


def _dividir_por_artigos(texto: str) -> list[str]:
    ocorrencias = list(PADRAO_ARTIGO.finditer(texto))

    if not ocorrencias:
        return []

    blocos = []

    if ocorrencias[0].start() > 0:
        introducao = texto[: ocorrencias[0].start()].strip()

        if introducao:
            blocos.append(introducao)

    for indice, ocorrencia in enumerate(ocorrencias):
        inicio = ocorrencia.start()

        if indice + 1 < len(ocorrencias):
            fim = ocorrencias[indice + 1].start()
        else:
            fim = len(texto)

        bloco = texto[inicio:fim].strip()

        if bloco:
            blocos.append(bloco)

    return blocos


def _dividir_texto_generico(
    texto: str,
    tamanho: int,
    sobreposicao: int,
) -> list[str]:
    chunks = []

    inicio = 0
    tamanho_texto = len(texto)

    while inicio < tamanho_texto:
        fim = min(
            inicio + tamanho,
            tamanho_texto,
        )

        if fim < tamanho_texto:
            ponto_quebra_minimo = inicio + max(sobreposicao + 1, tamanho // 2)
            ponto_quebra = texto.rfind(
                "\n\n",
                ponto_quebra_minimo,
                fim,
            )

            if ponto_quebra >= ponto_quebra_minimo:
                fim = ponto_quebra
            else:
                ponto_quebra = texto.rfind(
                    ". ",
                    ponto_quebra_minimo,
                    fim,
                )

                if ponto_quebra >= ponto_quebra_minimo:
                    fim = ponto_quebra + 1

        chunk = texto[inicio:fim].strip()

        if chunk:
            chunks.append(chunk)

        if fim >= tamanho_texto:
            break

        inicio = max(
            fim - sobreposicao,
            inicio + 1,
        )

    return chunks
