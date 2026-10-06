"""Baixa e valida localmente os pesos oficiais do Whisper large-v3."""

from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

MODEL_URL = (
    "https://openaipublic.azureedge.net/main/whisper/models/"
    "e5b1a55b89c1367dacf97e3e19bfd829a01529dbfdeefa8caeb59b3f1b81dadb/"
    "large-v3.pt"
)
MODEL_SHA256 = "e5b1a55b89c1367dacf97e3e19bfd829a01529dbfdeefa8caeb59b3f1b81dadb"
DEFAULT_DESTINATION = Path(__file__).resolve().parents[1] / "models" / "large-v3.pt"
CHUNK_SIZE = 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(CHUNK_SIZE), b""):
            digest.update(bloco)
    return digest.hexdigest()


def download_modelo(
    destino: Path = DEFAULT_DESTINATION,
    *,
    url: str = MODEL_URL,
    sha256_esperado: str = MODEL_SHA256,
    abrir_url=urlopen,
) -> Path:
    destino = Path(destino)
    if destino.is_file():
        if _sha256(destino) == sha256_esperado:
            return destino
        raise FileExistsError(
            "O destino já contém um arquivo diferente; ele foi preservado. "
            "Escolha outro destino ou confira o arquivo manualmente."
        )

    destino.parent.mkdir(parents=True, exist_ok=True)
    descritor, caminho_temporario = tempfile.mkstemp(
        prefix="whisper-large-v3-",
        suffix=".download",
        dir=destino.parent,
    )
    temporario = Path(caminho_temporario)
    request = Request(url, headers={"User-Agent": "Tabeleao-local-model-setup"})
    bytes_recebidos = 0
    proximo_aviso = 128 * 1024 * 1024
    try:
        with os.fdopen(descritor, "wb") as saida, abrir_url(
            request, timeout=60
        ) as resposta:
            while bloco := resposta.read(CHUNK_SIZE):
                saida.write(bloco)
                bytes_recebidos += len(bloco)
                if bytes_recebidos >= proximo_aviso:
                    print(
                        f"Baixados {bytes_recebidos / 1024**2:.0f} MB...",
                        flush=True,
                    )
                    proximo_aviso += 128 * 1024 * 1024

        if _sha256(temporario) != sha256_esperado:
            raise RuntimeError(
                "A verificação SHA-256 do modelo falhou; o arquivo incompleto "
                "não será instalado."
            )

        if destino.exists():
            raise FileExistsError(
                "O destino apareceu durante o download; ele foi preservado."
            )
        os.replace(temporario, destino)
        return destino
    finally:
        temporario.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Instala localmente os pesos oficiais do Whisper large-v3."
    )
    parser.add_argument(
        "--destino",
        type=Path,
        default=DEFAULT_DESTINATION,
        help=f"Caminho do checkpoint (padrão: {DEFAULT_DESTINATION})",
    )
    args = parser.parse_args()
    destino = download_modelo(args.destino)
    print(f"Whisper large-v3 instalado e validado ({destino.stat().st_size / 1024**3:.2f} GB).")


if __name__ == "__main__":
    main()
