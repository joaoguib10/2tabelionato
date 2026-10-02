import subprocess
from pathlib import Path

import pytest
from app.services import local_ocr
from app.services.document_processor import (
    ExtracaoDocumento,
    ParteExtraida,
    aplicar_ocr,
)


def tsv(nota=95, texto="Texto sintetico"):
    return (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tconf\ttext\n5\t1\t1\t1\t1\t"
        + str(nota)
        + "\t"
        + texto
        + "\n"
    )


@pytest.mark.parametrize("nota,aceitavel", [(95, True), (79, False), (0, False)])
def test_qualidade_tecnica(nota, aceitavel):
    assert local_ocr.interpretar_tsv(tsv(nota)) == ("Texto sintetico", aceitavel)


def test_sem_texto_nao_aprovado():
    assert local_ocr.interpretar_tsv("") == ("", False)


def test_motor_ausente_aviso_seguro(monkeypatch):
    monkeypatch.setattr(local_ocr.shutil, "which", lambda _: None)
    resultado = aplicar_ocr(
        Path("privado.pdf"),
        ExtracaoDocumento([ParteExtraida(1, "", situacao="NECESSITA_OCR")]),
    )
    assert resultado.situacao == "NECESSITA_OCR"
    assert "privado" not in str(resultado.resumo())


def test_idioma_ausente(monkeypatch):
    monkeypatch.setattr(local_ocr.shutil, "which", lambda x: x)
    monkeypatch.setattr(local_ocr, "_executar", lambda *a: "eng\n")
    monkeypatch.setenv("OCR_LANGUAGES", "por+eng")
    with pytest.raises(local_ocr.OCRIndisponivel, match="idiomas"):
        local_ocr.OCRLocal()


@pytest.mark.parametrize("sucesso", [True, False])
def test_pdf_misto_somente_pagina_pendente(monkeypatch, sucesso):
    chamadas = []

    class Motor:
        def pagina(self, caminho, numero):
            chamadas.append(numero)
            return "Texto reconhecido", sucesso

    monkeypatch.setattr(local_ocr, "OCRLocal", Motor)
    resultado = aplicar_ocr(
        Path("a.pdf"),
        ExtracaoDocumento(
            [
                ParteExtraida(1, "Texto nativo"),
                ParteExtraida(2, "Cabecalho", situacao="NECESSITA_OCR"),
                ParteExtraida(3, "", situacao="VAZIA"),
            ]
        ),
    )
    assert chamadas == [2]
    assert resultado.partes[0].conteudo == "Texto nativo"
    assert resultado.partes[1].conteudo == (
        "Texto reconhecido" if sucesso else "Cabecalho"
    )
    assert resultado.situacao == (
        "PROCESSADO_COMPLETO" if sucesso else "EXTRACAO_PARCIAL"
    )
    assert resultado.resumo()["partes_com_ocr"] == int(sucesso)


def test_timeout_nao_expoe_comando(monkeypatch):
    def falhar(*args, **kwargs):
        raise subprocess.TimeoutExpired("segredo", 1)

    monkeypatch.setattr(local_ocr.subprocess, "run", falhar)
    with pytest.raises(local_ocr.OCRIndisponivel) as erro:
        local_ocr._executar(["privado"], 1)
    assert "segredo" not in str(erro.value) and "privado" not in str(erro.value)


@pytest.mark.parametrize("falhar", [False, True])
def test_temporarios_removidos_inclusive_falha(monkeypatch, tmp_path, falhar):
    monkeypatch.setattr(local_ocr.shutil, "which", lambda x: x)
    caminhos = []

    def executar(args, timeout):
        if "--list-langs" in args:
            return "por\neng\n"
        if "-singlefile" in args:
            caminhos.append(Path(args[-1]).parent)
            assert caminhos[-1].is_dir()
            return ""
        if falhar:
            raise local_ocr.OCRIndisponivel("Falha controlada.")
        return tsv()

    monkeypatch.setattr(local_ocr, "_executar", executar)
    motor = local_ocr.OCRLocal()
    if falhar:
        with pytest.raises(local_ocr.OCRIndisponivel):
            motor.pagina(tmp_path / "a.pdf", 1)
    else:
        assert motor.pagina(tmp_path / "a.pdf", 1)[1]
    assert caminhos and all(not p.exists() for p in caminhos)


def test_limite_paginas(monkeypatch):
    monkeypatch.setattr(local_ocr.shutil, "which", lambda x: x)
    monkeypatch.setattr(local_ocr, "_executar", lambda *a: "por\neng\n")
    monkeypatch.setenv("OCR_MAX_PAGES_PER_DOCUMENT", "100")
    motor = local_ocr.OCRLocal()
    motor.paginas = 100
    with pytest.raises(local_ocr.OCRIndisponivel, match="Limite"):
        motor.pagina(Path("a.pdf"), 101)
