"""OCR sem rede: Poppler e Tesseract, em processos limitados e temporários."""

import csv
import io
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from app.config import (
    OCR_DOCUMENT_TIMEOUT_SECONDS,
    OCR_LANGUAGES,
    OCR_MAX_PAGES_PER_DOCUMENT,
    OCR_PAGE_TIMEOUT_SECONDS,
    OCR_PDFTOPPM_COMMAND,
    OCR_RENDER_DPI,
    OCR_TESSERACT_COMMAND,
)


class OCRIndisponivel(Exception):
    """Falha pública genérica; nunca inclui stderr, conteúdo ou caminhos."""


def _executar(args, timeout):
    if timeout <= 0:
        raise OCRIndisponivel("Limite de execução do OCR atingido.")
    try:
        return subprocess.run(
            args,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            env={**os.environ, "OMP_THREAD_LIMIT": "1"},
        ).stdout
    except (OSError, subprocess.SubprocessError):
        raise OCRIndisponivel(
            "OCR local indisponível ou limite de execução atingido."
        ) from None


def interpretar_tsv(tsv):
    linhas, notas = {}, []
    for item in csv.DictReader(
        io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE
    ):
        if item.get("level") != "5" or not (item.get("text") or "").strip():
            continue
        nota = float(item["conf"])
        if not 0 <= nota <= 100:
            raise ValueError("Resultado OCR inválido.")
        chave = tuple(item[k] for k in ("page_num", "block_num", "par_num", "line_num"))
        linhas.setdefault(chave, []).append(item["text"].strip())
        notas.append(nota)
    texto = "\n".join(" ".join(palavras) for palavras in linhas.values())
    # Heurística técnica conservadora, não confiança jurídica calibrada.
    aceitavel = (
        bool(notas)
        and sum(notas) / len(notas) >= 80
        and sum(n < 60 for n in notas) / len(notas) <= 0.1
    )
    return texto, aceitavel


class OCRLocal:
    def __init__(self):
        self.poppler = shutil.which(
            os.getenv("OCR_PDFTOPPM_COMMAND", OCR_PDFTOPPM_COMMAND)
        )
        self.tesseract = shutil.which(
            os.getenv("OCR_TESSERACT_COMMAND", OCR_TESSERACT_COMMAND)
        )
        self.idioma = os.getenv("OCR_LANGUAGES", OCR_LANGUAGES)
        self.maximo_paginas = max(
            1,
            int(
                os.getenv("OCR_MAX_PAGES_PER_DOCUMENT", str(OCR_MAX_PAGES_PER_DOCUMENT))
            ),
        )
        self.prazo_pagina = max(
            10,
            int(os.getenv("OCR_PAGE_TIMEOUT_SECONDS", str(OCR_PAGE_TIMEOUT_SECONDS))),
        )
        prazo_documento = max(
            self.prazo_pagina,
            int(
                os.getenv(
                    "OCR_DOCUMENT_TIMEOUT_SECONDS",
                    str(OCR_DOCUMENT_TIMEOUT_SECONDS),
                )
            ),
        )
        self.dpi = min(
            400,
            max(150, int(os.getenv("OCR_RENDER_DPI", str(OCR_RENDER_DPI)))),
        )
        self.prazo = time.monotonic() + prazo_documento
        self.paginas = 0
        if not self.poppler or not self.tesseract:
            raise OCRIndisponivel(
                "Instale/configure Poppler e Tesseract para executar OCR local."
            )
        idiomas = _executar([self.tesseract, "--list-langs"], 10).splitlines()
        if not all(i in idiomas for i in self.idioma.split("+")):
            raise OCRIndisponivel("Instale os idiomas configurados para OCR local.")

    def pagina(self, caminho: Path, numero: int):
        if self.paginas >= self.maximo_paginas or time.monotonic() >= self.prazo:
            raise OCRIndisponivel(
                "Limite de OCR por documento atingido; páginas pendentes exigem revisão."
            )
        self.paginas += 1
        prazo_pagina = min(self.prazo, time.monotonic() + self.prazo_pagina)
        with tempfile.TemporaryDirectory(prefix="tabeleao-ocr-") as pasta:
            prefixo = str(Path(pasta) / "pagina")
            _executar(
                [
                    self.poppler,
                    "-f",
                    str(numero),
                    "-l",
                    str(numero),
                    "-singlefile",
                    "-r",
                    str(self.dpi),
                    "-scale-to",
                    "3500",
                    "-gray",
                    "-png",
                    str(caminho.resolve()),
                    prefixo,
                ],
                prazo_pagina - time.monotonic(),
            )
            tsv = _executar(
                [
                    self.tesseract,
                    prefixo + ".png",
                    "stdout",
                    "-l",
                    self.idioma,
                    "tsv",
                ],
                prazo_pagina - time.monotonic(),
            )
            try:
                return interpretar_tsv(tsv)
            except (KeyError, TypeError, ValueError):
                raise OCRIndisponivel(
                    "Resultado OCR inválido; a página exige revisão."
                ) from None


def ocr_imagem(caminho: Path) -> tuple[str, bool]:
    """Lê uma imagem isolada localmente, sem exigir Poppler nem enviar dados à rede."""
    comando = shutil.which(os.getenv("OCR_TESSERACT_COMMAND", OCR_TESSERACT_COMMAND))
    if not comando:
        raise OCRIndisponivel("Instale/configure Tesseract para executar OCR local.")
    idiomas = os.getenv("OCR_LANGUAGES", OCR_LANGUAGES)
    disponiveis = _executar([comando, "--list-langs"], 10).splitlines()
    if not all(idioma in disponiveis for idioma in idiomas.split("+")):
        raise OCRIndisponivel("Instale os idiomas configurados para OCR local.")
    tsv = _executar(
        [comando, str(caminho.resolve()), "stdout", "-l", idiomas, "tsv"],
        max(10, OCR_PAGE_TIMEOUT_SECONDS),
    )
    try:
        return interpretar_tsv(tsv)
    except (KeyError, TypeError, ValueError):
        raise OCRIndisponivel("Resultado OCR inválido; a imagem exige revisão.") from None
