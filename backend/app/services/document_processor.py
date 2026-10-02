import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from pypdf import PdfReader

SITUACOES_EXTRACAO = {
    "PENDENTE_VERIFICACAO",
    "PROCESSADO_COMPLETO",
    "EXTRACAO_PARCIAL",
    "NECESSITA_OCR",
    "SEM_TEXTO",
    "ERRO_PROCESSAMENTO",
}
EXTRACOES_COMPLETAS = {"PROCESSADO_COMPLETO"}
TAMANHO_BLOCO_LOGICO = 6000


@dataclass
class ParteExtraida:
    numero: int
    conteudo: str
    metodo: str = "TEXTO"
    situacao: str = "EXTRAIDA"


@dataclass
class ExtracaoDocumento:
    partes: list[ParteExtraida]
    avisos: list[str] = field(default_factory=list)

    @property
    def situacao(self) -> str:
        com_texto = any(p.conteudo for p in self.partes)
        if any(p.situacao == "ERRO" for p in self.partes):
            return "EXTRACAO_PARCIAL" if com_texto else "ERRO_PROCESSAMENTO"
        pendentes = any(p.situacao == "NECESSITA_OCR" for p in self.partes)
        if pendentes:
            return "EXTRACAO_PARCIAL" if com_texto else "NECESSITA_OCR"
        if self.avisos:
            return "EXTRACAO_PARCIAL" if com_texto else "SEM_TEXTO"
        return "PROCESSADO_COMPLETO" if com_texto else "SEM_TEXTO"

    def resumo(self) -> dict:
        return {
            "versao_extrator": "2.2",
            "partes_originais": len(self.partes),
            "partes_com_texto": sum(bool(p.conteudo) for p in self.partes),
            "partes_necessitam_ocr": sum(
                p.situacao == "NECESSITA_OCR" for p in self.partes
            ),
            "partes_vazias": sum(p.situacao == "VAZIA" for p in self.partes),
            "partes_com_erro": sum(p.situacao == "ERRO" for p in self.partes),
            "partes_com_ocr": sum(p.metodo == "OCR_LOCAL" for p in self.partes),
            "partes_pendentes": [
                p.numero for p in self.partes if p.situacao in {"NECESSITA_OCR", "ERRO"}
            ],
            "caracteres_extraidos": sum(len(p.conteudo) for p in self.partes),
            "avisos": self.avisos,
        }


def _pdf_tem_imagem(recursos, visitados=None) -> bool:
    """Inclui imagens dentro de Form XObjects, sem decodificar pixels."""
    visitados = set() if visitados is None else visitados
    recursos = recursos.get_object() if hasattr(recursos, "get_object") else recursos
    objetos = (recursos or {}).get("/XObject", {})
    objetos = objetos.get_object() if hasattr(objetos, "get_object") else objetos
    for referencia in objetos.values():
        objeto = referencia.get_object()
        identidade = id(objeto)
        if identidade in visitados:
            continue
        visitados.add(identidade)
        if objeto.get("/Subtype") == "/Image":
            return True
        if objeto.get("/Subtype") == "/Form" and _pdf_tem_imagem(
            objeto.get("/Resources"), visitados
        ):
            return True
    return False


def _diagnosticar_pdf(caminho: Path) -> ExtracaoDocumento:
    partes = []
    for numero, pagina in enumerate(PdfReader(caminho).pages, 1):
        try:
            texto = limpar_texto_extraido(pagina.extract_text() or "")
            imagem = _pdf_tem_imagem(pagina.get("/Resources"))
            # Texto curto sobre imagem pode ser apenas um cabeçalho da digitalização.
            if imagem and len(texto) < 80:
                situacao = "NECESSITA_OCR"
            elif texto:
                situacao = "EXTRAIDA"
            else:
                conteudo = pagina.get_contents()
                situacao = (
                    "NECESSITA_OCR"
                    if conteudo and conteudo.get_data().strip()
                    else "VAZIA"
                )
            partes.append(ParteExtraida(numero, texto, situacao=situacao))
        except Exception:
            # Preserva a posição e não publica erros internos ou texto nos logs.
            partes.append(ParteExtraida(numero, "", situacao="ERRO"))
    return ExtracaoDocumento(partes)


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _blocos_word(elemento):
    """Percorre o XML em ordem, inclusive tabelas aninhadas, sem duplicar mesclas."""
    if elemento.tag == W + "del":
        return
    if elemento.tag == W + "p":

        def texto_no(no):
            if no.tag == W + "del":
                return ""
            if no.tag == W + "t":
                return no.text or ""
            if no.tag in {W + "tab", W + "br", W + "cr"}:
                return "\n" if no.tag != W + "tab" else "\t"
            return "".join(texto_no(filho) for filho in no)

        texto = limpar_texto_extraido(texto_no(elemento))
        if texto:
            yield texto
        return
    for filho in elemento:
        yield from _blocos_word(filho)


def _agrupar_blocos_logicos(
    blocos: list[str],
    limite: int = TAMANHO_BLOCO_LOGICO,
) -> list[str]:
    """Agrupa texto sem inventar páginas físicas e evita uma única parte gigante."""

    partes: list[str] = []
    atual: list[str] = []
    tamanho_atual = 0

    def concluir_atual() -> None:
        nonlocal atual, tamanho_atual
        if atual:
            partes.append("\n\n".join(atual).strip())
            atual = []
            tamanho_atual = 0

    for bloco_original in blocos:
        restante = bloco_original.strip()
        while restante:
            espaco = limite - tamanho_atual
            if atual and len(restante) + 2 > espaco:
                concluir_atual()
                espaco = limite

            if len(restante) <= espaco:
                atual.append(restante)
                tamanho_atual += len(restante) + (2 if tamanho_atual else 0)
                restante = ""
                continue

            corte = restante.rfind(" ", 0, espaco)
            if corte < max(1, espaco // 2):
                corte = espaco
            atual.append(restante[:corte].strip())
            concluir_atual()
            restante = restante[corte:].strip()

    concluir_atual()
    return [parte for parte in partes if parte]


def _diagnosticar_docx(caminho: Path) -> ExtracaoDocumento:
    if not validar_docx(caminho):
        raise ValueError("O arquivo DOCX não é válido.")
    blocos, avisos = [], []
    with zipfile.ZipFile(caminho) as arquivo:
        nomes = ["word/document.xml"] + sorted(
            n
            for n in arquivo.namelist()
            if n.startswith(("word/header", "word/footer"))
            and n.endswith(".xml")
            or n in {"word/footnotes.xml", "word/endnotes.xml"}
        )
        for nome in nomes:
            raiz = ET.fromstring(arquivo.read(nome))
            blocos.extend(_blocos_word(raiz))
            tags = {no.tag.rsplit("}", 1)[-1] for no in raiz.iter()}
            if tags & {"drawing", "pict", "object", "altChunk"}:
                avisos.append(
                    "Imagens ou objetos incorporados exigem conferência; podem conter texto não extraído."
                )
            if tags & {"ins", "del"}:
                avisos.append(
                    "Alterações controladas encontradas; a versão exibida exige conferência."
                )
    partes_texto = _agrupar_blocos_logicos(blocos)
    return ExtracaoDocumento(
        [
            ParteExtraida(numero, texto, situacao="EXTRAIDA")
            for numero, texto in enumerate(partes_texto, 1)
        ]
        or [ParteExtraida(1, "", situacao="VAZIA")],
        list(dict.fromkeys(avisos)),
    )


def aplicar_ocr(caminho: Path, extracao: ExtracaoDocumento) -> ExtracaoDocumento:
    from app.services.local_ocr import OCRIndisponivel, OCRLocal

    pendentes = [p for p in extracao.partes if p.situacao == "NECESSITA_OCR"]
    if not pendentes:
        return extracao
    try:
        motor = OCRLocal()
    except OCRIndisponivel as erro:
        extracao.avisos.append(str(erro))
        return extracao
    for parte in pendentes:
        try:
            texto, aceitavel = motor.pagina(caminho, parte.numero)
            texto = limpar_texto_extraido(texto)
            if texto and aceitavel:
                # Renderiza a página inteira, evitando duplicar o cabeçalho nativo.
                parte.conteudo = texto
                parte.metodo = "OCR_LOCAL"
                parte.situacao = "EXTRAIDA"
            else:
                extracao.avisos.append(
                    "OCR sem qualidade suficiente; confira as páginas pendentes no original."
                )
        except OCRIndisponivel as erro:
            extracao.avisos.append(str(erro))
    extracao.avisos = list(dict.fromkeys(extracao.avisos))
    return extracao


def extrair_documento(
    caminho_arquivo: str,
    *,
    executar_ocr: bool | None = None,
    forcar_ocr: bool = False,
) -> ExtracaoDocumento:
    caminho = Path(caminho_arquivo)
    if not caminho.is_file():
        raise FileNotFoundError("Arquivo indisponível para processamento.")
    if caminho.suffix.lower() == ".pdf":
        extracao = _diagnosticar_pdf(caminho)
        if forcar_ocr:
            for parte in extracao.partes:
                parte.situacao = "NECESSITA_OCR"
        habilitado = (
            os.getenv("OCR_ENABLED", "true").lower() == "true"
            if executar_ocr is None
            else executar_ocr
        )
        habilitado = habilitado or forcar_ocr
        return aplicar_ocr(caminho, extracao) if habilitado else extracao
    if caminho.suffix.lower() == ".docx":
        return _diagnosticar_docx(caminho)
    if caminho.suffix.lower() == ".txt":
        paginas = extrair_paginas_txt(caminho)
        return ExtracaoDocumento([ParteExtraida(n, t) for n, t in paginas])
    if caminho.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        from app.services.local_ocr import OCRIndisponivel, ocr_imagem

        habilitado = (
            os.getenv("OCR_ENABLED", "true").lower() == "true"
            if executar_ocr is None
            else executar_ocr
        ) or forcar_ocr
        if not habilitado:
            return ExtracaoDocumento(
                [ParteExtraida(1, "", situacao="NECESSITA_OCR")]
            )
        try:
            texto, aceitavel = ocr_imagem(caminho)
        except OCRIndisponivel as erro:
            return ExtracaoDocumento(
                [ParteExtraida(1, "", situacao="NECESSITA_OCR")], [str(erro)]
            )
        texto = limpar_texto_extraido(texto)
        if not texto or not aceitavel:
            return ExtracaoDocumento(
                [ParteExtraida(1, "", situacao="NECESSITA_OCR")],
                ["OCR da imagem exige revisão; envie uma cópia mais legível."],
            )
        return ExtracaoDocumento([ParteExtraida(1, texto, metodo="OCR_LOCAL")])
    raise ValueError(
        "Formato não suportado para extração. Envie PDF, DOCX, TXT, JPG ou PNG."
    )


def limpar_texto_extraido(texto: str) -> str:
    """Remove caracteres de controle incompatíveis com PostgreSQL e prompts."""
    return "".join(
        caractere
        for caractere in texto
        if caractere in {"\n", "\r", "\t"} or ord(caractere) >= 32
    ).strip()


def extrair_paginas_pdf(
    caminho: Path,
) -> list[tuple[int, str]]:
    leitor = PdfReader(caminho)

    paginas = []

    for numero_pagina, pagina in enumerate(
        leitor.pages,
        start=1,
    ):
        texto = pagina.extract_text()

        if texto:
            texto = limpar_texto_extraido(texto)

        if texto:
            paginas.append(
                (
                    numero_pagina,
                    texto,
                )
            )

    return paginas


def extrair_paginas_docx(
    caminho: Path,
) -> list[tuple[int, str]]:
    return [
        (p.numero, p.conteudo) for p in _diagnosticar_docx(caminho).partes if p.conteudo
    ]


def extrair_paginas_txt(
    caminho: Path,
) -> list[tuple[int, str]]:
    try:
        texto = caminho.read_text(encoding="utf-8")
        texto = limpar_texto_extraido(texto)

    except UnicodeDecodeError:
        texto = caminho.read_text(encoding="latin-1")
        texto = limpar_texto_extraido(texto)

    if not texto:
        return []

    blocos = [bloco for bloco in texto.split("\n\n") if bloco.strip()]
    partes = _agrupar_blocos_logicos(blocos or [texto])
    return list(enumerate(partes, 1))


def validar_docx(
    caminho: Path,
) -> bool:
    try:
        with zipfile.ZipFile(
            caminho,
            "r",
        ) as arquivo_zip:
            return "word/document.xml" in arquivo_zip.namelist()

    except zipfile.BadZipFile:
        return False


def extrair_paginas(
    caminho_arquivo: str,
) -> list[tuple[int, str]]:
    caminho = Path(caminho_arquivo)

    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")

    extensao = caminho.suffix.lower()

    if extensao == ".pdf":
        paginas = extrair_paginas_pdf(caminho)

    elif extensao == ".docx":
        if not validar_docx(caminho):
            raise ValueError("O arquivo DOCX não é válido.")

        paginas = extrair_paginas_docx(caminho)

    elif extensao == ".txt":
        paginas = extrair_paginas_txt(caminho)

    else:
        raise ValueError(f"Tipo de arquivo não suportado: {extensao}")

    if not paginas:
        if extensao == ".pdf":
            raise ValueError(
                "PDF sem camada de texto. OCR necessário antes do processamento."
            )
        raise ValueError("Não foi possível extrair texto do documento.")

    return paginas
