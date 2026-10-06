import hashlib
import io

import pytest
from scripts.download_whisper_model import download_modelo


class RespostaFalsa(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_download_modelo_grava_apenas_arquivo_com_hash_valido(tmp_path):
    conteudo = b"pesos-sinteticos"
    destino = tmp_path / "large-v3.pt"
    hash_esperado = hashlib.sha256(conteudo).hexdigest()

    resultado = download_modelo(
        destino,
        url="https://example.invalid/model.pt",
        sha256_esperado=hash_esperado,
        abrir_url=lambda request, timeout: RespostaFalsa(conteudo),
    )

    assert resultado == destino
    assert destino.read_bytes() == conteudo


def test_download_modelo_preserva_destino_existente_incorreto(tmp_path):
    destino = tmp_path / "large-v3.pt"
    destino.write_bytes(b"arquivo-existente")

    with pytest.raises(FileExistsError):
        download_modelo(
            destino,
            url="https://example.invalid/model.pt",
            sha256_esperado=hashlib.sha256(b"outro-arquivo").hexdigest(),
            abrir_url=lambda request, timeout: pytest.fail(
                "não deve substituir nem baixar sobre um arquivo preexistente"
            ),
        )

    assert destino.read_bytes() == b"arquivo-existente"


def test_download_modelo_rejeita_hash_invalido_e_remove_temporario(tmp_path):
    destino = tmp_path / "large-v3.pt"

    with pytest.raises(RuntimeError, match="SHA-256"):
        download_modelo(
            destino,
            url="https://example.invalid/model.pt",
            sha256_esperado="0" * 64,
            abrir_url=lambda request, timeout: RespostaFalsa(b"pesos-invalidos"),
        )

    assert not destino.exists()
    assert not list(tmp_path.glob("whisper-large-v3-*.download"))
