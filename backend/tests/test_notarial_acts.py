import io
import zipfile
from pathlib import Path

from app.models import AtaTrabalho
from app.routers import notarial_acts
from app.services import notarial_act_service


def _zip_conversa(nome="_chat.txt", conteudo=None):
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr(
            nome,
            conteudo
            or "[9/6/25, 9:21:33 PM] Você: mensagem sintética\ncontinuação da mensagem\n[10/28/25, 8:41:35 AM] Pessoa: resposta sintética",
        )
    return memoria.getvalue()


def test_ata_zip_organiza_e_descarta_todos_os_temporarios(
    client,
    db,
    testing_session_factory,
    usuario_factory,
    auth_headers,
    tmp_path,
    monkeypatch,
):
    usuario = usuario_factory("ata-local")
    raiz = tmp_path / "atas"
    raiz.mkdir()
    monkeypatch.setattr(notarial_acts, "UPLOAD_DIR", raiz)
    monkeypatch.setattr(notarial_act_service, "SessionLocal", testing_session_factory)
    resposta = client.post(
        "/api/atas",
        headers=auth_headers(usuario),
        files={"arquivo": ("exportacao.zip", _zip_conversa(), "application/zip")},
    )
    assert resposta.status_code == 202
    dados = client.get(
        f"/api/atas/{resposta.json()['id']}", headers=auth_headers(usuario)
    ).json()
    assert dados["status"] == "PRONTO"
    assert "continuação da mensagem" in dados["resultado"]
    assert "\n" not in dados["resultado"]
    trabalho = db.query(AtaTrabalho).one()
    pasta = Path(trabalho.caminho_temporario).parent
    assert pasta.exists()
    exclusao = client.delete(f"/api/atas/{trabalho.id}", headers=auth_headers(usuario))
    assert exclusao.status_code == 204
    assert db.query(AtaTrabalho).count() == 0
    assert not pasta.exists()


def test_ata_bloqueia_traversal_e_isola_usuario(
    client,
    db,
    testing_session_factory,
    usuario_factory,
    auth_headers,
    tmp_path,
    monkeypatch,
):
    dono = usuario_factory("ata-dono")
    outro = usuario_factory("ata-outro")
    raiz = tmp_path / "atas"
    raiz.mkdir()
    monkeypatch.setattr(notarial_acts, "UPLOAD_DIR", raiz)
    monkeypatch.setattr(notarial_act_service, "SessionLocal", testing_session_factory)
    resposta = client.post(
        "/api/atas",
        headers=auth_headers(dono),
        files={
            "arquivo": (
                "exportacao.zip",
                _zip_conversa("../fora.txt"),
                "application/zip",
            )
        },
    )
    assert resposta.status_code == 202
    assert (
        client.get(
            f"/api/atas/{resposta.json()['id']}", headers=auth_headers(dono)
        ).json()["status"]
        == "ERRO"
    )
    trabalho = db.query(AtaTrabalho).one()
    assert (
        client.get(f"/api/atas/{trabalho.id}", headers=auth_headers(outro)).status_code
        == 404
    )
    assert not (tmp_path / "fora.txt").exists()


def test_transcricao_usa_modelo_whisper_ja_armazenado_localmente(
    tmp_path,
    monkeypatch,
):
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"audio-sintetico")
    modelo = tmp_path / "small.pt"
    modelo.write_bytes(b"modelo-sintetico")
    argumentos = []

    monkeypatch.setattr(notarial_act_service, "WHISPER_MODEL_PATH", str(modelo))
    monkeypatch.setattr(
        notarial_act_service.shutil,
        "which",
        lambda comando: "ffmpeg.exe" if "ffmpeg" in comando else "whisper.exe",
    )

    def executar(comando, **_opcoes):
        argumentos.extend(comando)
        pasta_saida = Path(comando[comando.index("--output_dir") + 1])
        (pasta_saida / "audio.txt").write_text(
            "transcrição sintética", encoding="utf-8"
        )

    monkeypatch.setattr(notarial_act_service.subprocess, "run", executar)

    assert notarial_act_service._transcrever_audio(audio) == "transcrição sintética"
    assert argumentos[argumentos.index("--model") + 1] == "small"
    assert argumentos[argumentos.index("--model_dir") + 1] == str(tmp_path)


def test_ata_preserva_referencia_de_imagem_no_fluxo_textual(
    client,
    testing_session_factory,
    usuario_factory,
    auth_headers,
    tmp_path,
    monkeypatch,
):
    usuario = usuario_factory("ata-anexo")
    raiz = tmp_path / "atas"
    raiz.mkdir()
    monkeypatch.setattr(notarial_acts, "UPLOAD_DIR", raiz)
    monkeypatch.setattr(notarial_act_service, "SessionLocal", testing_session_factory)
    conteudo = "[9/6/25, 9:21:33 PM] Você: IMG-20260909-WA0001.jpg (arquivo anexado)"
    resposta = client.post(
        "/api/atas",
        headers=auth_headers(usuario),
        files={
            "arquivo": (
                "exportacao.zip",
                _zip_conversa(conteudo=conteudo),
                "application/zip",
            )
        },
    )
    assert resposta.status_code == 202
    dados = client.get(
        f"/api/atas/{resposta.json()['id']}", headers=auth_headers(usuario)
    ).json()
    assert "IMG-20260909-WA0001.jpg (arquivo anexado)" in dados["resultado"]
    assert "Anexo visual não incluído" not in dados["resultado"]
    assert dados["diagnostico"]["referencias_anexos_preservadas"] is True


def test_ata_parcial_pode_repetir_transcricao_local(
    client,
    testing_session_factory,
    usuario_factory,
    auth_headers,
    tmp_path,
    monkeypatch,
):
    usuario = usuario_factory("ata-repetir")
    raiz = tmp_path / "atas"
    raiz.mkdir()
    monkeypatch.setattr(notarial_acts, "UPLOAD_DIR", raiz)
    monkeypatch.setattr(notarial_act_service, "SessionLocal", testing_session_factory)
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr("_chat.txt", "[9/6/25, 9:21:33 PM] Você: audio-teste.opus")
        pacote.writestr("audio-teste.opus", b"audio-sintetico")
    monkeypatch.setattr(
        notarial_act_service, "_transcrever_audio", lambda _arquivo: None
    )
    monkeypatch.setattr(
        notarial_act_service, "_duracao_audio", lambda _arquivo: "00:21s"
    )
    resposta = client.post(
        "/api/atas",
        headers=auth_headers(usuario),
        files={"arquivo": ("exportacao.zip", memoria.getvalue(), "application/zip")},
    )
    assert resposta.status_code == 202
    identificador = resposta.json()["id"]
    assert (
        client.get(f"/api/atas/{identificador}", headers=auth_headers(usuario)).json()[
            "status"
        ]
        == "PRONTO_PARCIAL"
    )
    monkeypatch.setattr(
        notarial_act_service, "_transcrever_audio", lambda _arquivo: "fala sintética"
    )
    repeticao = client.post(
        f"/api/atas/{identificador}/reprocessar", headers=auth_headers(usuario)
    )
    assert repeticao.status_code == 202
    final = client.get(
        f"/api/atas/{identificador}", headers=auth_headers(usuario)
    ).json()
    assert final["status"] == "PRONTO"
    assert "(Áudio de 00:21s): fala sintética" in final["resultado"]
